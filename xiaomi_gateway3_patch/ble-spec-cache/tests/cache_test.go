package cachetest

import (
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "testing"

 luajson "github.com/layeh/gopher-json"
 lua "github.com/yuin/gopher-lua"
)
type sent struct {to int; raw string}
type harness struct {l *lua.LState;t *testing.T;clock float64;root string;sent []sent;pub []map[string]interface{}}
func newHarness(t *testing.T,root string)*harness {
 t.Helper();if root==""{root=t.TempDir()};h:=&harness{l:lua.NewState(),t:t,clock:100,root:root}
 h.l.PreloadModule("json",luajson.Loader)
 conf:=h.l.NewTable();conf.RawSetString("root",lua.LString(root));conf.RawSetString("now",h.l.NewFunction(func(l *lua.LState)int{l.Push(lua.LNumber(h.clock));return 1}));h.l.SetGlobal("GW2_BLE_CACHE_TEST",conf)
 h.l.SetGlobal("miio_send",h.l.NewFunction(func(l *lua.LState)int{h.sent=append(h.sent,sent{l.ToInt(1),l.ToString(2)});return 0}))
 h.l.SetGlobal("mosquitto_pub",h.l.NewFunction(func(l *lua.LState)int{var v map[string]interface{};if err:=json.Unmarshal([]byte(l.ToString(2)),&v);err!=nil{t.Fatal(err)};h.pub=append(h.pub,v);return 0}))
 if err:=h.l.DoFile("../src/spec-cache.lua");err!=nil{t.Fatal(err)}
 t.Cleanup(h.l.Close);return h
}
func (h *harness) call(name string,args ...lua.LValue)[]lua.LValue {
 h.t.Helper();before:=h.l.GetTop()
 if err:=h.l.CallByParam(lua.P{Fn:h.l.GetGlobal(name),NRet:lua.MultRet,Protect:true},args...);err!=nil{h.t.Fatal(err)}
 var ret []lua.LValue;for i:=before+1;i<=h.l.GetTop();i++{ret=append(ret,h.l.Get(i))};h.l.SetTop(before);return ret
}
func (h *harness) req(id,pid,off int)string {
 s:=mustJSON(map[string]interface{}{"id":id,"method":"_sync.ble_spec_query_prod","params":map[string]int{"pdid":pid,"offset":off}})
 if r:=h.call("miio_request",lua.LNumber(2),lua.LString("_sync.ble_spec_query_prod"),lua.LString(s));len(r)!=0{h.t.Fatal("request not passed through")};return s
}
func mustJSON(v interface{})string {b,e:=json.Marshal(v);if e!=nil{panic(e)};return string(b)}
func rule(piid int)map[string]interface{} {return map[string]interface{}{"siid":2,"piid":piid,"type":"uint8","intvl":0,"delta":0}}
func page(pid,size,ttl int,props ...int)map[string]interface{} {
 a:=[]interface{}{};for _,i:=range props{a=append(a,rule(i))};return map[string]interface{}{"pdid":pid,"size":size,"ttl":ttl,"pidrule":a,"eidrule":[]interface{}{}}
}
func (h *harness) res(to int,req string,r interface{})[]lua.LValue {return h.call("miio_response",lua.LNumber(to),lua.LString("_sync.ble_spec_query_prod"),lua.LString(req),lua.LString(mustJSON(r)))}
func TestOpenmiioMappedRequestAndRestoredResponseIDs(t *testing.T){
 h:=newHarness(t,"");h.state("cloud_connected");q:=h.req(41,6281,0)
 // Upstream MarkMessage mutates the stored request ID. FindMessage restores
 // only the response ID; request and response IDs differ in the Lua hook.
 var wire map[string]interface{};json.Unmarshal([]byte(q),&wire);wire["id"]=9001
 h.res(2,mustJSON(wire),map[string]interface{}{"id":41,"result":page(6281,1,1800,1)})
 if _,err:=os.Stat(filepath.Join(h.root,"products.json"));err!=nil{t.Fatal("mapped foreground cloud response was not learned",err)}
 h.state("cloud_retry");h.state("cloud_connected");h.tick(3)
 refresh:=h.pub[0];original:=refresh["id"];refresh["id"]=9002
 ret:=h.res(-1,mustJSON(refresh),map[string]interface{}{"id":original,"result":page(6281,1,2400,2)})
 if len(ret)!=1||ret[0]!=lua.LNil{t.Fatal("mapped refresh not consumed")}
 h.state("cloud_retry");h.req(42,6281,0)
 if h.last()["result"].(map[string]interface{})["pidrule"].([]interface{})[0].(map[string]interface{})["piid"]!=float64(2){t.Fatal("mapped refresh did not update cache")}
}
func TestReportedOnlineDoesNotHideSpecTimeout(t *testing.T){
 h:=newHarness(t,"");h.state("cloud_connected");q:=h.req(77,6281,0);h.tick(6)
 read:=func()map[string]interface{}{raw,e:=os.ReadFile(filepath.Join(h.root,"status.json"));if e!=nil{t.Fatal(e)};var v map[string]interface{};if e=json.Unmarshal(raw,&v);e!=nil{t.Fatal(e)};return v}
 s:=read();if s["cloud_state"]!="degraded"||s["reported_cloud_state"]!="online"||s["revision"]!=float64(4){t.Fatal(s)}
 // Repeated stock 'online' reports must not erase query failure evidence.
 h.state("cloud_connected");h.tick(6);if read()["cloud_state"]!="degraded"{t.Fatal("stock report hid the timeout")}
 var wire map[string]interface{};json.Unmarshal([]byte(q),&wire);wire["id"]=9010
 h.res(2,mustJSON(wire),map[string]interface{}{"id":77,"result":page(6281,1,1800,1)})
 h.tick(6);s=read();if s["cloud_state"]!="online"||s["complete_products"]!=float64(1){t.Fatal(s)}
}
func (h *harness) tick(dt float64){h.clock+=dt;h.call("mosquitto_sub",lua.LString("gw2/ble-spec-cache/tick"),lua.LString("1"))}
func (h *harness) state(s string){h.call("miio_response",lua.LNumber(2),lua.LString("local.query_status"),lua.LString(`{"id":99,"method":"local.query_status"}`),lua.LString(mustJSON(map[string]interface{}{"id":99,"params":s})))}
func (h *harness) learn(pid int){r:=h.req(1,pid,0);if v:=h.res(2,r,map[string]interface{}{"id":1,"result":page(pid,1,1800,1)});len(v)!=0{h.t.Fatal("fresh cloud response suppressed")}}
func (h *harness) last()map[string]interface{} {h.t.Helper();var v map[string]interface{};if len(h.sent)==0{h.t.Fatal("no response")};if e:=json.Unmarshal([]byte(h.sent[len(h.sent)-1].raw),&v);e!=nil{h.t.Fatal(e)};return v}
func TestCloudFirstAndOfflinePersistence(t *testing.T){
 h:=newHarness(t,"");h.state("cloud_connected");h.learn(6281)
 if len(h.sent)!=0{t.Fatal("sent unsolicited response")}
 raw,e:=os.ReadFile(filepath.Join(h.root,"products.json"));if e!=nil{t.Fatal(e)}
 var disk map[string]interface{};if e=json.Unmarshal(raw,&disk);e!=nil{t.Fatal(e)}
 h.state("cloud_retry");h.req(2,6281,0);v:=h.last();r:=v["result"].(map[string]interface{})
 if r["ttl"]!=float64(120)||v["id"]!=float64(2){t.Fatal(v)}
 if _,ok:=r["eidrule"].([]interface{});!ok{t.Fatalf("empty array changed type: %s",h.sent[len(h.sent)-1].raw)}
 h2:=newHarness(t,h.root);h2.state("cloud_retry");h2.req(3,6281,0);if h2.last()["result"]==nil{t.Fatal("persisted cache not loaded")}
}
func TestTimeoutFallbackAndLateCloudReplacement(t *testing.T){
 h:=newHarness(t,"");h.learn(6281);req:=h.req(2,6281,0)
 if len(h.sent)!=0{t.Fatal("did not wait for cloud")};h.tick(3)
 if h.last()["result"]==nil{t.Fatal("no timeout fallback")}
 if ret:=h.res(2,req,map[string]interface{}{"id":2,"result":page(6281,1,2400,2)});len(ret)!=1||ret[0]!=lua.LNil{t.Fatal("late cloud duplicated reply")}
 h.state("cloud_retry");h.req(3,6281,0);r:=h.last()["result"].(map[string]interface{})
 if r["pidrule"].([]interface{})[0].(map[string]interface{})["piid"]!=float64(2){t.Fatal("fresh late response not learned")}
}
func TestIncompletePagesNeverReplaceCompleteCache(t *testing.T){
 h:=newHarness(t,"");h.learn(6281)
 q:=h.req(10,6281,0);h.res(2,q,map[string]interface{}{"id":10,"result":page(6281,2,2000,2)})
 h.state("cloud_retry");h.req(11,6281,0);r:=h.last()["result"].(map[string]interface{})
 if r["size"]!=float64(1){t.Fatal("partial cache promoted")}
}
func TestMultiPageOfflineAndNoCrossProduct(t *testing.T){
 h:=newHarness(t,"");q:=h.req(1,6281,0);h.res(2,q,map[string]interface{}{"id":1,"result":page(6281,2,1800,1)})
 q=h.req(2,6281,1);h.res(2,q,map[string]interface{}{"id":2,"result":page(6281,2,1800,2)})
 h.state("cloud_retry");h.req(3,6281,0);h.req(4,6281,1)
 if len(h.sent)!=2||h.last()["result"]==nil{t.Fatal("offline pagination")}
 h.req(5,999,0);if h.last()["error"]==nil{t.Fatal("cross-product cache reuse")}
}
func TestReconnectProactiveRefreshCloudOnly(t *testing.T){
 h:=newHarness(t,"");h.learn(6281);h.state("cloud_retry");h.state("cloud_connected");h.tick(3)
 if len(h.pub)!=1{t.Fatal("no reconnect refresh")};req:=h.pub[0]
 if req["_to"]!=float64(0){t.Fatal("refresh not routed to cloud")}
 raw:=mustJSON(req);v:=h.res(-1,raw,map[string]interface{}{"id":req["id"],"result":page(6281,1,3600,3)})
 if len(v)!=1||v[0]!=lua.LNil{t.Fatal("private refresh leaked")}
 if len(h.sent)!=0{t.Fatal("proactive refresh injected into radio")}
 h.state("cloud_retry");h.req(3,6281,0);if h.last()["result"].(map[string]interface{})["pidrule"].([]interface{})[0].(map[string]interface{})["piid"]!=float64(3){t.Fatal("reconnect kept stale cache")}
}
func TestExplicitDenialAndZeroTTLInvalidate(t *testing.T){
 for _,result:=range []map[string]interface{}{{"error":map[string]interface{}{"code":-1,"message":"permission denied"}},{"result":page(6281,1,0,1)}}{
  h:=newHarness(t,"");h.learn(6281);req:=h.req(2,6281,0);result["id"]=2
  if len(h.res(2,req,result))!=0{t.Fatal("denial suppressed")};h.state("cloud_retry");h.req(3,6281,0)
  if h.last()["error"]==nil{t.Fatal("withdrawn cache still used")}
 }
}
func TestCorruptDiskAndUnrelatedMessages(t *testing.T){
 root:=t.TempDir();os.WriteFile(filepath.Join(root,"products.json"),[]byte("bad json"),0600);h:=newHarness(t,root)
 if r:=h.call("miio_request",lua.LNumber(2),lua.LString("properties_changed"),lua.LString(`{"method":"properties_changed","params":[]}`));len(r)!=0{t.Fatal(r)}
 h.state("cloud_retry");h.req(1,6281,0);if h.last()["error"]==nil{t.Fatal("cold cache fabricated")}
}
func TestStaleTransactionCannotOverwriteNewerCloudRules(t *testing.T){
 h:=newHarness(t,"");old:=h.req(1,6281,0);fresh:=h.req(2,6281,0)
 h.res(2,fresh,map[string]interface{}{"id":2,"result":page(6281,1,1800,2)})
 h.res(2,old,map[string]interface{}{"id":1,"result":page(6281,1,1800,1)})
 h.state("cloud_retry");h.req(3,6281,0)
 r:=h.last()["result"].(map[string]interface{})
 if r["pidrule"].([]interface{})[0].(map[string]interface{})["piid"]!=float64(2){t.Fatal("old transaction replaced fresh rule")}
}
func TestOfflinePaginationDoesNotWaitPerPage(t *testing.T){
 h:=newHarness(t,"");q:=h.req(1,6281,0);h.res(2,q,map[string]interface{}{"id":1,"result":page(6281,2,1800,1)})
 q=h.req(2,6281,1);h.res(2,q,map[string]interface{}{"id":2,"result":page(6281,2,1800,2)})
 h.req(3,6281,0);h.tick(3);if len(h.sent)!=1{t.Fatal("first page fallback missing")}
 h.req(4,6281,1);if len(h.sent)!=2{t.Fatal("second cached page delayed")}
}
func TestNetworkErrorFallbackAndCloudPriorityOnRecovery(t *testing.T){
 h:=newHarness(t,"");h.learn(6281);q:=h.req(2,6281,0)
 v:=h.res(2,q,map[string]interface{}{"id":2,"error":map[string]interface{}{"code":-10000,"message":"network timeout"}})
 if len(v)!=1||v[0]!=lua.LNil||h.last()["result"]==nil{t.Fatal("network error not covered")}
 h.state("cloud_retry");h.state("cloud_connected");n:=len(h.sent);q=h.req(3,6281,0)
 if len(h.sent)!=n{t.Fatal("online request answered from old cache immediately")}
 if len(h.res(2,q,map[string]interface{}{"id":3,"result":page(6281,1,3600,3)}))!=0{t.Fatal("fresh response not passed")}
}
func TestDuplicateAndMalformedPagesDoNotPromote(t *testing.T){
 h:=newHarness(t,"");h.learn(6281)
 q:=h.req(2,6281,0);h.res(2,q,map[string]interface{}{"id":2,"result":page(6281,2,1800,2)})
 q=h.req(3,6281,1);h.res(2,q,map[string]interface{}{"id":3,"result":page(6281,2,1800,2)})
 q=h.req(4,6281,0);bad:=page(6281,1,1800,3);bad["size"]=99;h.res(2,q,map[string]interface{}{"id":4,"result":bad})
 h.state("cloud_retry");h.req(5,6281,0)
 r:=h.last()["result"].(map[string]interface{})
 if r["pidrule"].([]interface{})[0].(map[string]interface{})["piid"]!=float64(1){t.Fatal("bad pages changed cache")}
}
func TestCacheExcludesUnexpectedPayloadFields(t *testing.T){
 h:=newHarness(t,"");q:=h.req(1,6281,0);r:=page(6281,1,1800,1)
 r["token"]="unexpected-secret";r["pidrule"].([]interface{})[0].(map[string]interface{})["beaconkey"]="unexpected-secret"
 h.res(2,q,map[string]interface{}{"id":1,"result":r})
 data,e:=os.ReadFile(filepath.Join(h.root,"products.json"));if e!=nil{t.Fatal(e)}
 var saved interface{};if e=json.Unmarshal(data,&saved);e!=nil{t.Fatal(e)}
 h.state("cloud_retry");h.req(2,6281,0)
 if strings.Contains(string(data),"unexpected-secret")||strings.Contains(h.sent[len(h.sent)-1].raw,"unexpected-secret"){t.Fatal("non-spec fields persisted")}
}
func TestStockWireIDsAndEventReportingFields(t *testing.T){
 h:=newHarness(t,"");q:=h.req(1,6281,0)
 p:=rule(1001);event:=map[string]interface{}{"siid":2,"eiid":1001,"intvl":30,"delta":1,"piids":[]interface{}{map[string]interface{}{"piid":1002,"type":"uint8"}}}
 result:=map[string]interface{}{"pdid":6281,"ttl":1800,"size":2,"pidrule":[]interface{}{p},"eidrule":[]interface{}{event}}
 h.res(2,q,map[string]interface{}{"id":1,"result":result})
 if _,e:=os.Stat(filepath.Join(h.root,"products.json"));e!=nil{t.Fatal("stock 1000-based wire IDs rejected",e)}
 h.state("cloud_retry");h.req(2,6281,0)
 r:=h.last()["result"].(map[string]interface{});e:=r["eidrule"].([]interface{})[0].(map[string]interface{})
 if e["eiid"]!=float64(1001)||e["intvl"]!=float64(30)||e["delta"]!=float64(1){t.Fatal("required event fields lost",e)}
}
func TestNewProductRefreshDoesNotWaitForPeriodicSweep(t *testing.T){
 h:=newHarness(t,"");h.state("cloud_connected");h.tick(3)
 // An empty periodic sweep has scheduled its next pass five minutes away.
 h.req(1,6281,0);h.tick(2)
 if len(h.pub)!=1{t.Fatal("new product waited for periodic sweep instead of prompt refresh")}
 if h.pub[0]["params"].(map[string]interface{})["pdid"]!=float64(6281){t.Fatal(h.pub)}
}
func TestExplicitColdLearningWithoutStockQuery(t *testing.T){
 h:=newHarness(t,"")
 h.call("mosquitto_sub",lua.LString("gw2/ble-spec-cache/learn"),lua.LString("6281"))
 if len(h.pub)!=1{t.Fatal("cold learning did not query cloud")}
 req:=h.pub[0];id:=req["id"];req["id"]=9100
 h.res(-1,mustJSON(req),map[string]interface{}{"id":id,"result":page(6281,1,1800,1001)})
 h.state("cloud_retry");h.req(2,6281,0)
 if h.last()["result"]==nil{t.Fatal("manually learned rules not available offline")}
}
