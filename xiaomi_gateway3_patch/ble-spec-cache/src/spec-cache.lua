-- GW2 BLE Spec cache, runtime extension for unmodified openmiio_agent 1.2.1.
-- Lua 5.1 / gopher-lua compatible. No radio, memory or firmware modification.
local json = require("json")
local test = rawget(_G, "GW2_BLE_CACHE_TEST")
local ROOT = test and test.root or "/data/ble-spec-cache"
local STATUS = test and (test.root .. "/status.json") or "/tmp/gw2-ble-spec-cache-status.json"
local CACHE = ROOT .. "/products.json"
local METHOD = "_sync.ble_spec_query_prod"
local TICK = "gw2/ble-spec-cache/tick"
local OFFLINE_TTL, TIMEOUT, MAX_PIDS = 120, 2, 200
local cache, known, pending, transactions = {}, {}, {}, {}
local generations = {}
local committed_generations = {}
local background, queue, queued = {}, {}, {}
local state, degraded, epoch = "unknown", false, 0
local seq, next_background, last_status = 1600000000, 0, -10
local background_job = nil
local last_cloud_success = nil
local last_response = nil
local manual_learn = false
local runtime_pid=0
if not test then
  local pf=io.open("/proc/self/stat","r")
  if pf then runtime_pid=tonumber((pf:read("*l") or ""):match("^(%d+)")) or 0;pf:close() end
end
local stats = {cloud_pages=0, learned_products=0, cache_replies=0, cache_misses=0,
  ticks=0,requests=0,responses=0,invalid_responses=0,cloud_errors=0,manual_learn_requests=0,
  timeouts=0, invalid_pages=0, refresh_ok=0, refresh_fail=0, errors=0}
local function now()
  if test then return test.now() end
  local f=io.open("/proc/uptime", "r")
  if not f then return os.time() end
  local s=f:read("*l"); f:close()
  return tonumber(s and s:match("^[%d%.]+")) or os.time()
end
local function decode(s)
  if type(s)~="string" or #s>2097152 then return nil end
  local ok,v=pcall(json.decode,s)
  if ok and type(v)=="table" then return v end
end
local function integer(v,lo,hi)
  return type(v)=="number" and v==math.floor(v) and v>=lo and v<=hi
end
local function count(t,max)
  if type(t)~="table" then return nil end
  local n=0
  for k in pairs(t) do
    if not integer(k,1,max) then return nil end
    n=n+1
  end
  if n>#t or n>max then return nil end
  return n
end
local function atomic(path,data)
  local f=io.open(path..".new","w")
  if not f then return false end
  local ok=f:write(data); local closed=f:close()
  if not ok or not closed then os.remove(path..".new"); return false end
  if not os.rename(path..".new",path) then os.remove(path..".new"); return false end
  return true
end
local function nentries(t) local n=0;for _ in pairs(t) do n=n+1 end;return n end
local function status(force)
  if not force and now()-last_status<5 then return end
  last_status=now()
  local products={}
  for pid,r in pairs(cache) do products[#products+1]={pdid=tonumber(pid),size=r.size,pages=nentries(r.pages),source_ttl=r.source_ttl} end
  table.sort(products,function(a,b)return a.pdid<b.pdid end)
  local effective=state=="offline" and "offline" or degraded and "degraded" or last_cloud_success and "online" or "unverified"
  atomic(STATUS,json.encode({patch="gw2-ble-spec-cache-v1",policy="cloud-first",
    revision=4,runtime_pid=runtime_pid,observed_uptime=now(),last_response=last_response,
    cloud_state=effective,reported_cloud_state=state,
    last_cloud_success_uptime=last_cloud_success,transport_degraded=degraded,epoch=epoch,products=products,
    known_products=nentries(known),complete_products=nentries(cache),pending=nentries(pending),
    refresh_queued=#queue,refresh_active=background_job~=nil,statistics=stats}))
end
local types={bool=true,int8=true,int16=true,int32=true,uint8=true,uint16=true,uint32=true,float=true,string=true}
local function page_valid(r,pid,offset)
  if type(r)~="table" or r.pdid~=pid or not integer(r.ttl,0,4294967295) or
    not integer(r.size,0,15) or not integer(offset,0,15) then return false end
  local a,b=count(r.pidrule,15),count(r.eidrule,15)
  if not a or not b or a+b>r.size or offset+a+b>r.size or (a+b==0 and offset<r.size) then return false end
  for _,v in ipairs(r.pidrule) do
    -- Validate the uint8/uint16 wire fields, not the compact in-memory IDs.
    -- Stock subtracts 1000 from property/event IDs before packing them.
    if type(v)~="table" or not integer(v.siid,1,255) or not integer(v.piid,1,65535) or not types[v.type] then return false end
    if not integer(v.intvl,0,4294967295) then return false end
    if v.delta~=nil and (type(v.delta)~="number" or v.delta~=v.delta or math.abs(v.delta)==math.huge) then return false end
  end
  for _,v in ipairs(r.eidrule) do
    if type(v)~="table" or not integer(v.siid,1,255) or not integer(v.eiid,1,65535) then return false end
    if not integer(v.intvl,0,4294967295) or not integer(v.delta,0,4294967295) then return false end
    local c=count(v.piids,12);if not c then return false end
    for _,x in ipairs(v.piids) do
      if type(x)~="table" or not integer(x.piid,1,65535) or not types[x.type] then return false end
    end
  end
  return true,a+b
end
local function known_pid(pid)
  local key=tostring(pid)
  if not known[key] and nentries(known)>=MAX_PIDS then return false end
  if not known[key] then
    known[key]=true
    if not queued[key] and #queue<MAX_PIDS then queue[#queue+1]=pid;queued[key]=true end
    next_background=math.min(next_background,now()+1)
  end
  return true
end
local function persist()
  if not atomic(CACHE,json.encode({schema=1,products=cache})) then stats.errors=stats.errors+1;return false end
  return true
end
local function invalidate(pid)
  local key=tostring(pid)
  if cache[key] then cache[key]=nil;persist() end
end
local function remember(tx,r,offset)
  local valid,num=page_valid(r,tx.pid,offset)
  if not valid or r.ttl==0 or tx.bad or offset~=tx.next or (tx.size and tx.size~=r.size) then
    tx.bad=true;stats.invalid_pages=stats.invalid_pages+1;return false
  end
  local clean={pdid=r.pdid,ttl=r.ttl,size=r.size,pidrule={},eidrule={}}
  tx.seen=tx.seen or {}
  for _,v in ipairs(r.pidrule) do
    local id="p:"..v.siid..":"..v.piid
    if tx.seen[id] then tx.bad=true;stats.invalid_pages=stats.invalid_pages+1;return false end
    tx.seen[id]=true
    clean.pidrule[#clean.pidrule+1]={siid=v.siid,piid=v.piid,type=v.type,intvl=v.intvl,delta=v.delta}
  end
  for _,v in ipairs(r.eidrule) do
    local id="e:"..v.siid..":"..v.eiid
    if tx.seen[id] then tx.bad=true;stats.invalid_pages=stats.invalid_pages+1;return false end
    tx.seen[id]=true;local event={siid=v.siid,eiid=v.eiid,intvl=v.intvl,delta=v.delta,piids={}}
    for _,x in ipairs(v.piids) do event.piids[#event.piids+1]={piid=x.piid,type=x.type} end
    clean.eidrule[#clean.eidrule+1]=event
  end
  tx.size=r.size;tx.next=offset+num;tx.pages[tostring(offset)]={raw=json.encode(clean),count=num}
  tx.source_ttl=r.ttl
  if tx.next~=tx.size then return true,false end
  if tx.generation<(committed_generations[tostring(tx.pid)] or 0) then
    tx.complete=true;return true,true -- Never replace a newer completed rule set.
  end
  -- Merely starting a newer refresh must not invalidate a valid foreground
  -- result: that refresh may fail or time out without yielding any rules.
  committed_generations[tostring(tx.pid)]=tx.generation
  local record={pages=tx.pages,size=tx.size,source_ttl=tx.source_ttl}
  local old=cache[tostring(tx.pid)]
  if not old or json.encode(old)~=json.encode(record) then
    cache[tostring(tx.pid)]=record;persist()
  end
  tx.complete=true;stats.learned_products=stats.learned_products+1
  return true,true
end
local function new_tx(pid)
  local key=tostring(pid);generations[key]=(generations[key] or 0)+1
  return {pid=pid,next=0,pages={},started=now(),epoch=epoch,generation=generations[key]}
end
local function cache_page(pid,offset)
  local record=cache[tostring(pid)]
  local page=record and record.pages[tostring(offset)]
  if not page then return nil end
  local r=decode(page.raw)
  if not page_valid(r,pid,offset) or r.ttl==0 then return nil end
  r.ttl=OFFLINE_TTL
  return r
end
local function send_fallback(p)
  if p.served then return end
  local r=cache_page(p.pid,p.offset)
  if r then
    miio_send(2,json.encode({id=p.id,result=r}))
    stats.cache_replies=stats.cache_replies+1
    p.tx.offline_reply=true
  else
    miio_send(2,json.encode({id=p.id,error={code=-32001,message="BLE Spec offline cache unavailable"}}))
    stats.cache_misses=stats.cache_misses+1
  end
  p.served=true;p.retain_until=now()+60
end
local function enqueue(pid)
  local key=tostring(pid)
  if not queued[key] and #queue<MAX_PIDS then queue[#queue+1]=pid;queued[key]=true end
end
local function real_state(s)
  if s=="cloud_connected" then
    if state~="online" then
      state="online";degraded=false;epoch=epoch+1
      -- Discard partial background transactions from a previous connectivity epoch.
      background={};background_job=nil;queue={};queued={}
      for pid in pairs(known) do enqueue(tonumber(pid)) end
      next_background=now()+2
    end
  elseif s=="cloud_trying" or s=="cloud_retry" or s=="wifi_disconnected" or s=="wifi_connecting" then
    if state~="offline" then
      state="offline";epoch=epoch+1
      background={};background_job=nil;queue={};queued={}
    end
  end
end
local function response_page(pid,offset,res)
  if type(res.result)=="table" and res.result.pdid==pid and res.result.ttl==0 then return "withdrawn" end
  if res.result and page_valid(res.result,pid,offset) then return "success" end
  if res.result~=nil then return "invalid" end
  local e=res.error;local message=type(e)=="table" and e.message or e
  message=type(message)=="string" and message:lower() or ""
  for _,word in ipairs({"denied","forbidden","permission","unauthor","invalid","not found","unsupported","unbind","deleted"}) do
    if message:find(word,1,true) then return "denied" end
  end
  for _,word in ipairs({"timeout","timed out","offline","network","connection","not connected"}) do
    if message:find(word,1,true) then return "network" end
  end
  return state=="offline" and "network" or "error"
end
local function observe_response(pid,offset,kind,res)
  stats.responses=stats.responses+1
  if kind=="invalid" then stats.invalid_responses=stats.invalid_responses+1 end
  if res.error~=nil then stats.cloud_errors=stats.cloud_errors+1 end
  -- Structural diagnostics only: no response body, device identifiers or keys.
  last_response={pdid=pid,offset=offset,kind=kind,result_type=type(res.result)}
  if type(res.error)=="table" and integer(res.error.code,-2147483648,2147483647) then last_response.error_code=res.error.code end
  if type(res.result)=="table" then
    local r=res.result
    last_response.pdid_type=type(r.pdid);last_response.ttl_type=type(r.ttl);last_response.size_type=type(r.size)
    last_response.property_count=count(r.pidrule,15);last_response.event_count=count(r.eidrule,15)
    if integer(r.size,0,65535) then last_response.size=r.size end
  end
end
local function refresh_send(job)
  seq=seq+1;if seq>=2000000000 then seq=1600000000 end
  local id=seq
  background[tostring(id)]={job=job,deadline=now()+3,epoch=epoch}
  job.id=id
  -- Use normal openmiio routing/ID mapping. Responses are returned to MQTT
  -- and observed in our to=-1 response hook, rather than inventing wire IDs.
  mosquitto_pub("miio/command",json.encode({id=id,_to=0,method=METHOD,params={pdid=job.pid,offset=job.tx.next}}),false)
end
local function request(from,method,raw)
  local req=decode(raw);if not req then return end
  if from==0 and method=="local.status" then real_state(req.params);return end
  if from~=2 or method~=METHOD then return end
  local p=req.params
  if type(p)~="table" or not integer(p.pdid,1,65535) or not integer(p.offset or 0,0,15) or not integer(req.id,0,2147483647) then return end
  if not known_pid(p.pdid) then return end
  stats.requests=stats.requests+1
  local key=tostring(p.pdid);local offset=p.offset or 0
  local tx=transactions[key]
  if offset==0 or not tx or now()-tx.started>30 then tx=new_tx(p.pdid);transactions[key]=tx end
  if nentries(pending)>=128 then stats.errors=stats.errors+1;return end
  local item={id=req.id,pid=p.pdid,offset=offset,deadline=now()+TIMEOUT,retain_until=now()+60,tx=tx}
  pending[tostring(req.id)]=item
  -- Still forward every original query to the cloud. When already offline,
  -- return cached pages immediately so a multi-page query fits its 10s buffer.
  if state=="offline" or degraded or tx.offline_reply then send_fallback(item) end
end
local function response(to,method,request_raw,response_raw)
  local req,res=decode(request_raw),decode(response_raw)
  if not req or not res then return end
  if method=="local.query_status" and type(res.params)=="string" then real_state(res.params);return end
  if method~=METHOD then return end
  -- MarkMessage changes the stored request ID. FindMessage restores only
  -- res.id, so correlation must use the response's restored caller ID.
  if not integer(res.id,0,2147483647) then return end
  local correlation=tostring(res.id)
  if to==-1 then
    local b=background[correlation]
    if not b then return end
    if type(req.params)~="table" or req.params.pdid~=b.job.pid or (req.params.offset or 0)~=b.job.tx.next then return end
    background[correlation]=nil
    if b.epoch~=epoch then return true end
    local job=b.job;local kind=response_page(job.pid,job.tx.next,res)
    observe_response(job.pid,job.tx.next,kind,res)
    if kind=="withdrawn" or kind=="denied" then invalidate(job.pid) end
    if kind=="success" then
      stats.cloud_pages=stats.cloud_pages+1;degraded=false;last_cloud_success=now()
      local ok,done=remember(job.tx,res.result,job.tx.next)
      if ok and not done then refresh_send(job);return true end
      if done then stats.refresh_ok=stats.refresh_ok+1 else stats.refresh_fail=stats.refresh_fail+1 end
    else
      stats.refresh_fail=stats.refresh_fail+1
      if kind=="network" then degraded=true end
    end
    background_job=nil;next_background=now()+2
    return true -- Our private refresh must not become a HA command response.
  end
  if to~=2 then return end
  local p=pending[correlation]
  if not p then return end
  if type(req.params)~="table" or req.params.pdid~=p.pid or (req.params.offset or 0)~=p.offset then return end
  pending[correlation]=nil
  local kind=response_page(p.pid,p.offset,res)
  observe_response(p.pid,p.offset,kind,res)
  if kind=="success" then
    stats.cloud_pages=stats.cloud_pages+1;degraded=false;last_cloud_success=now()
    remember(p.tx,res.result,p.offset)
    if p.served then return true end
    return -- Fresh cloud response, unchanged, goes to the original BLE caller.
  end
  if kind=="withdrawn" or kind=="denied" then invalidate(p.pid) end
  if p.served then return true end
  if kind=="network" then
    degraded=true;send_fallback(p)
    return true
  end
  return -- Explicit denial/malformed/unknown errors are never hidden by cache.
end
local function tick()
  stats.ticks=stats.ticks+1
  for id,p in pairs(pending) do
    if now()>=p.retain_until then pending[id]=nil
    elseif not p.served and now()>=p.deadline then
      stats.timeouts=stats.timeouts+1;degraded=true;send_fallback(p)
    end
  end
  for id,b in pairs(background) do
    if now()>=b.deadline then
      background[id]=nil;background_job=nil;stats.refresh_fail=stats.refresh_fail+1;degraded=true;next_background=now()+5
    end
  end
  if (state=="online" or manual_learn) and not background_job and now()>=next_background then
    local pid=table.remove(queue,1)
    if pid then
      manual_learn=false;queued[tostring(pid)]=nil;background_job={pid=pid,tx=new_tx(pid)};refresh_send(background_job)
    else
      -- Revisit known products periodically; reconnect is not the only
      -- opportunity to replace stale cache. Never answer a refresh from cache.
      for key in pairs(known) do enqueue(tonumber(key)) end
      next_background=now()+300
    end
  end
  status(false)
end
local function guard(f,...)
  local ok,result=pcall(f,...)
  if not ok then
    stats.errors=stats.errors+1
    -- No payloads, keys or exception strings go into diagnostic output.
    if stats.errors<=3 then print("[ble-spec-cache] callback error; original message preserved") end
    return false,nil
  end
  return true,result
end
-- openmiio uses no return values for pass-through, one nil to suppress.
function miio_request(from,method,raw)
  guard(request,from,method,raw)
end
function miio_response(to,method,req,res)
  local ok,suppress=guard(response,to,method,req,res)
  if ok and suppress==true then return nil end
end
function mosquitto_sub(topic,payload)
  if topic==TICK and payload=="1" then guard(tick) end
  if topic=="gw2/ble-spec-cache/learn" and type(payload)=="string" and #payload<=5 and payload:match("^%d+$") then
    guard(function()
      local pid=tonumber(payload)
      if not integer(pid,1,65535) or not known_pid(pid) then return end
      if background_job and background_job.pid==pid then return end
      -- Explicit cloud-only learning: does not fake connectivity or restart BLE.
      for i=#queue,1,-1 do if queue[i]==pid then table.remove(queue,i) end end
      table.insert(queue,1,pid);queued[tostring(pid)]=true
      manual_learn=true;next_background=now();stats.manual_learn_requests=stats.manual_learn_requests+1
      tick();status(true)
    end)
  end
end
-- Load only complete, revalidated, non-device-specific product rule sets.
local f=io.open(CACHE,"r")
if f then
  local raw=f:read(2097153);f:close();local saved=decode(raw)
  if saved and saved.schema==1 and type(saved.products)=="table" then
    local accepted=0
    for key,r in pairs(saved.products) do
      local pid=tonumber(key)
      if accepted<MAX_PIDS and integer(pid,1,65535) and type(r)=="table" and type(r.pages)=="table" then
        local tx=new_tx(pid);local offset=0
        for _=1,16 do
          local page=r.pages[tostring(offset)];local result=page and decode(page.raw)
          if not result then tx.bad=true;break end
          local valid,num=page_valid(result,pid,offset)
          if not valid or result.ttl==0 or (tx.size and tx.size~=result.size) then tx.bad=true;break end
          tx.size=result.size;tx.pages[tostring(offset)]=page;offset=offset+num
          if offset==tx.size then tx.complete=true;break end
        end
        if tx.complete and not tx.bad then
          cache[tostring(pid)]={pages=tx.pages,size=tx.size,source_ttl=r.source_ttl}
          known[tostring(pid)]=true;accepted=accepted+1
        end
      end
    end
  end
end
print("[ble-spec-cache] cloud-first Spec cache active; complete_products="..nentries(cache))
guard(status,true)
