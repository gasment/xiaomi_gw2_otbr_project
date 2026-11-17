#!/bin/sh

REVISION="2"
REVISION_FILE="/data/utils/fw_manager.revision"

#
# @file    fw_manager.sh
# @brief   This script is used to manage program operations,
#          including, but not limited to,
#          1. start user programs.
#          2. switch platform.
#          3. factory reset.
#          4. entry factory mode.
#          5. update firmware.
#
# @author  Michael (huiwang.zhu@aqara.com)
#
# Copyright (c) 2020~2021 ShenZhen Lumiunited Technology Co., Ltd.
# All rights reserved.
#

#
# Script options.
# -h: helper.
# -r: runner.
# -s: switcher.
# -f: factory.
# -u: update. 
# -t: test cases.
#
OPTIONS="-h;-r;-s;-f;-u;-t"

#
# Platforms.
# -a: AIOT.
# -m: MIOT.
#
PLATFORMS="-a;-m"

#
# Factory operations.
# -r: reset.
# -m: mode.
#
FACTORY="-r;-m"

#
# Factory operations.
# -s: check sign.
# -n: ignore sign.
#
UPDATER="-s;-n"

#
# Test cases.
# -a: set tag.
# -b: get tag.
# -c: value string to value.
# -d: stop AIOT platform process.
# -e: stop MIOT platform process.
# -f: create post_init.sh.
# -g: set hostname.
# -h: build hostname by model.
# -i: Disable uart.
# -j: Enable uart.
# -k: User behavior.
#
TESTCASES="-a;-b;-c;-d;-e;-f;-g;-h,-i,-j,-k"

#
# Default platform.
# Must in aiot;miot.
#
DEFAULT_PLATFORM="miot"

#
# Tag files.
#
MODEL_FILE="/data/utils/fw_manager.model"

IRCTRL_BIN_BK_="/data/IRController.bin"

#
# Product model
#
# note: default is unknow.
#
model=""

#
# Running options.
#
WIFI_START_PARAMS=""
FACTORY_RESTTING=0

#
# Enable debug, 0/1.
#
debug=1

GETPROP=agetprop
SETPROP=asetprop

#
# Show green content, in the same way to use as echo.
#
green_echo()
{
    if [ $debug -eq 0 ]; then return; fi

    GREEN="\033[0;32m"; BLACK="\033[0m"
    if [ "$1" = "-n" ]; then echo -en $GREEN$2$BLACK; else echo -e $GREEN$1$BLACK; fi
}

#
# Show red content, in the same way to use as echo.
#
red_echo()
{
	RED="\033[0;31m"; BLACK="\033[0m"
	if [ "$1" = "-n" ]; then echo -en $RED$2$BLACK; else echo -e $RED$1$BLACK; fi
}

#
# Match sub-string.
#
# param $1: string.
# Param $2: sub-string.
#
# return: 1 - matched.
# return: 0 - unmatch.
#
match_substring()
{
	string="$1"; substr="$2"

	case $string in
        *$substr*) return 1 ;;
        *)         return 0 ;;
	esac
}

#
# Convert rom string to number.
# Param: value string.
#
convert_str2int()
{
    local str=$1
    local length=${#str}
    local sum=0; local index=0

    while [ ${index} -lt ${length} ]; do
        let sum=10*sum+${str:${index}:1}
        let index+=1
    done

    echo ${sum}
}

#
# Set some tags into file.
# Param1: file.
# Param2: tags.
#
set_tags()
{
    local file="$1"
    local tags="$2"

    if [ ! -f "$file" ]; then
        local dir=`dirname "$file"`
        if [ ! -d "$dir" ]; then mkdir "$dir"; fi
    fi

    echo "$tags" > "$file"
}

#
# Get tags from file.
# Param1: file.
#
get_tags()
{
    if [ ! -f "$1" ]; then return "0"; fi

    local file="$1"
    local tags=`cat "$file"`

    return $tags
}

usage_helper()
{
    green_echo "Helper to show how to use this script."
    green_echo "Usage: fw_manager.sh -h [$OPTIONS]."
}

usage_runner()
{
    green_echo "Run the user programs."
    green_echo "Usage: fw_manager.sh -r [$PLATFORMS]."
    green_echo " -a : AIoT."
    green_echo " -m : MIoT."
    green_echo " If lost options($PLATFORMS), use slef-checking."
}

usage_switcher()
{
    green_echo "Switch programs."
    green_echo "Usage: fw_manager.sh -s [$PLATFORMS]."
    green_echo " -a : AIoT."
    green_echo " -m : MIoT."
    green_echo " If lost options($PLATFORMS), use slef-checking."
}

usage_factory()
{
    green_echo "Factory woker."
    green_echo "Usage: fw_manager.sh -f [$FACTORY]."
    green_echo " -r : factory reset."
    green_echo " -m : factory test mode."
}

usage_updater()
{
    green_echo "Update firmware."
    green_echo "Usage: fw_manager.sh -u [$UPDATER] [path]."
    green_echo " -s : check sign."
    green_echo " -n : don't check sign."
}

usage_tester()
{
    green_echo "Test cases."
    green_echo "Usage: fw_manager.sh -t [$TESTCASES] [params]."
    green_echo " -a [path] [tag]-: set tag."
    green_echo " -b [path]-------: get tag."
    green_echo " -c [string]-----: value string to value."
    green_echo " -d -------------: stop process(AIOT)."
    green_echo " -e -------------: stop process(MIOT)."
    green_echo " -f -------------: create post_init.sh."
    green_echo " -g [name]-------: set hostname."
    green_echo " -h [model]------: build hostname by model."
    green_echo " -i -------------: Disable Uart(Debug)."
    green_echo " -j -------------: Enable Uart(Debug)."
    green_echo " -k -------------: User behavior."
}

run_aiot_with_dbg()
{
    red_echo "AIOT is not supported yet!"
}

run_aiot_normally()
{
    red_echo "AIOT it not supported yet!"
}

wait_property_svr_ok()
{
    for i in `seq 10`;
    do
        sys_name=`${GETPROP} ro.sys.name`
        if [ x"$sys_name" != x ];then
            break;
        fi

        sleep 0.1
    done
}

check_mount()
{
    local res_m=`cat /proc/mounts  | grep res`
    if [ x"$res_m" = x ];then
        red_echo "error:no res"
        ubifs_format.sh 0 /res
        echo "reformat_res_`date`" >> /res/fac_key.log 
        res_m=`cat /proc/mounts  | grep res`
        if [ x"$res_m" = x ];then
            echo "mount res fail"
        else
            echo "mount res ok"
        fi
    fi

    local data_m=`cat /proc/mounts  | grep data`
    if [ x"$data_m" = x ];then
        red_echo "error:no data"
        ubifs_format.sh 1 /data
        echo "reformat_data_`date`" >> /res/fac_key.log 
        data_m=`cat /proc/mounts  | grep data`
        if [ x"$data_m" = x ];then
            red_echo "mount data fail"
        else
            green_echo "mount data ok"
            mkdir -p /data/storage
            factory_data restore
            sync
            sleep 0.2
            echo 3 >/proc/sys/vm/drop_caches

            if [ `pgrep property_service` ]; then
                killall property_service
            fi

            property_service -i /etc/build.prop -p /data/storage/prop.dat -b

            sleep 0.2
        fi
    fi
}

run_prepare()
{
    if [ ! -f /res/passwd ]; then
        green_echo "use default password"
        echo "root:qdGt8T0XjiWXI:0:0:Linux User,,,:/home/root:/bin/sh" > /res/passwd
    fi

    check_mount
    wait_property_svr_ok

    local check_mdnsd=`pstree | grep mdnsd`
    local check_mosqu=`pstree | grep mosquitto`
    local entry_facmd=`${GETPROP} persist.sys.factory_result`
    local check_syslogd=`pstree | grep syslogd`

    if [ "$check_mdnsd" = "" ]; then mdnsd        ;fi
    if [ "$check_mosqu" = "" ]; then mosquitto -d ;fi
    if [ "$check_syslogd" = "" ]; then syslogd -s 10240 -b0 ;fi

    if [ ! "$entry_facmd" = "true" ]; then
        /usr/factory_test/bin/start_fac.sh
        exit 0
    fi

    # Disable Uart.
    local debug_flag=`${GETPROP} persist.app.tty_enable`
    if [ ! "$debug_flag" = "true" ];  then
        /bin/riu_w 101e 53 3010
    fi
}

#
# Run programs for aiot-platform.
# Note: We can specifing some programs to ignored
#       by use of format string: "x;x;x...".
#
# Flag:
#       ha_agent : a
#       ha_basis : b
#
# For example: ignore ha_basis and ha_agent: run_aiot "a;b".
#
run_aiot()
{
    red_echo "AIOT it not supported yet!"
}

# Prepare data for mijia_automation
prepare_for_mijia_automation()
{
    local miio_conf="/data/miio/device.conf"
    local miio_token="/data/miio/device.token"
    local miio_token_file="/data/miio/device.token"
    local os_release_file="/tmp/os-release"
    local mi_did="`${GETPROP} persist.sys.miio_did`"
    local mi_model="`${GETPROP} persist.sys.model`"
    local mi_key="`${GETPROP} persist.sys.miio_key`"
    local mi_mac="`${GETPROP} persist.sys.miio_mac`"
    local mi_token="`${GETPROP} persist.app.miio_dtoken`"

    echo "did=${mi_did}" > $miio_conf
    echo "key=${mi_key}" >> $miio_conf
    echo "mac=${mi_mac}" >> $miio_conf
    echo "vendor=lumi"   >> $miio_conf
    echo "model=${mi_model}" >> $miio_conf
    echo  "${mi_token}" > $miio_token_file

    local version="`${GETPROP} ro.sys.mi_fw_ver`"
    if [ "x$version" = "x" ]; then version="`${GETPROP} ro.sys.fw_ver`"; fi

    local build_num="_`${GETPROP} ro.sys.mi_build_num`"
    if [ "$build_num" = "_" ]; then build_num="_`${GETPROP} ro.sys.build_num`"; fi

    local mi_version=$version$build_num
    if [ -z $mi_version ]; then mi_version="unknown"; fi

    echo "LUMI_VERSION=$mi_version" > $os_release_file
}

#
# Run programs for miot-platform.
# Note: We can specifing some programs to ignored
#       by use of format string: "x;x;x...".
#
# Flag: mha_basis  : b
#       miio_agent : g
#
# For example: ignore mha_basis and mha_master: run_miot "b;m".
#
run_miot()
{
    green_echo "run miot, model:$model"
 
    #
    # Set timezone
    #
    local timezone="$(${GETPROP} persist.app.miio_timezone)"
    if [ "x${timezone}" = "x" ]; then timezone="/usr/share/zoneinfo/Asia/Shanghai"; fi

    if [ -L /tmp/localtime ]; then rm /tmp/localtime; fi
    ln -sf $timezone /tmp/localtime

    [ "${model}" = "lumi.gateway.mcn001" ] && ${SETPROP} sys.miio_pid 5338
    [ "${model}" = "lumi.gateway.mgl001" ] && ${SETPROP} sys.miio_pid 9654

    if [ -f /var/TZ ]; then rm -f /var/TZ; fi

    local b=0; local g=0; local r=0;

    match_substring "$1" "b"; b=$?
    match_substring "$1" "g"; g=$?
    match_substring "$1" "r"; r=$?

    [ -d /data/miio ] || mkdir -p /data/miio
    [ -d /data/zoneinfo ] || mkdir -p /data/zoneinfo
    [ -d /data/log ] || mkdir -p /data/log
    [ -d /data/central_lite ] || mkdir -p /data/central_lite

    if [ $g -eq 0 ]; then
        miio_agent -l0 2>&1 > /dev/null &
        sleep 1
    fi

    if [ $b -eq 0 ]; then
        mha_basis > /dev/null 2>&1 &
    fi

# RCP mode disabled:     mZ3GatewayHost_MQTT -p /dev/ttyS1 -d /data/zigbee_host/ -r 'c' 2>&1 | logger -t "zigbee_host" &
    sleep 0.5
# RCP mode disabled:     mzigbee_agent -f /etc/mzigbeeAgent.conf 2>&1 | logger -t "zigbee_agent" &

    if [ "x$(ps | grep 'miio_client -l' | grep -v grep)" != "x" ]; then
        killall miio_client
        sleep 0.5
        if [ "x$(ps | grep miio_client -l)" != "x" ]; then
            killall -9 miio_client
        fi
    fi

    miio_client -l1 -d /data/miio/ -n128 2>&1 > /dev/null -D

    sleep 0.2

    mha_master --log-level 6 --background

    prepare_for_mijia_automation

    mijia_automation -d /data/miio 2>&1 | logger -t "mijia_automation" &

    # Start MIIO_BT
    [ -d /data/local/miio_bt ] || mkdir -p /data/local/miio_bt

    local pid_arg="$(${GETPROP} sys.miio_pid)"
    if [ "x$pid_arg" != "x" ]; then
        pid_arg="-p $pid_arg"
    fi

    miio_bt -l3 $pid_arg -b 2>&1 > /dev/null &

    # Waitting for other process to ready.
    sleep 1

    wifi_start.sh INIT

    cp="`${GETPROP} persist.app.cloud_provisioned`"
    hp="`${GETPROP} persist.app.hap_provisioned`"
    ka="`${GETPROP} persist.app.hap_keepalive`"

    if [ ! "$cp" = "true" ] && [ ! "$hp" = "true" ] && [ ! "$ka" = "true" ]; then
        wifi_start.sh AP "$WIFI_START_PARAMS"

        # Waittig for checking ethernet
        sleep 2
        lan_linked="`${GETPROP} sys.lan_linked`"
        if [ "x${lan_linked}" = "x" ]; then
            [ $(cat /sys/class/net/eth0/carrier) -eq 1 ] && lan_linked="true" || lan_linked="false"
        fi

        green_echo "lan_linked=$lan_linked"
        if [ "$lan_linked" != "true" -a "$model" = "lumi.gateway.mcn001" ]; then
            wifi_start.sh SET_APSTA_MODE
        fi
    else
        wifi_start.sh STA &
    fi

    if [ "$model" = "lumi.gateway.mcn001" -a "$cp" = "true" ]; then
        local miio_did="$(${GETPROP} persist.sys.miio_did)"
        # Launch miio central_lite
        if [ "x$(pgrep central_lite)" = "x" ]; then
            local cnt=0
            local valid="$(${GETPROP} sys.time_valid)"
            while [  "${valid}" != "true" -a $cnt -le 20 ];do
                valid="$(${GETPROP} sys.time_valid)"
                green_echo "Waittig for time ready"
                sleep 0.5
                let cnt++
            done
            central_lite -d $miio_did -p /data/central_lite > /dev/null 2>&1 &
        fi
    fi

    if [ $FACTORY_RESTTING -eq 0 ]; then
        query_zgb.sh &
    fi

    if [ "x$(ps grep miio_client_helper_nomqtt.sh | grep -v grep)" != "x" ]; then
        killall -9 miio_client_helper_nomqtt.sh
        sleep 0.2
        miio_client_helper_nomqtt.sh 2>&1 > /dev/console &
    fi

    # Run matter apps if required
    local matter_supported="$(${GETPROP} persist.sys.matter_supported)"
    if [ "$model" = "lumi.gateway.mgl001" -o "$matter_supported" = "true" ]; then
        ot_service > /dev/null 2>&1 &
        http_service > /dev/null 2>&1 &
        mkdir -p /data/matter
        matter_gateway_service -l info -f syslog -c /etc -d > /dev/null 2>&1 &
        translation_service --model /data/matter/translation/specv3_models --mapping-table /data/matter/translation/resources_dict > /dev/null 2>&1 &
    fi

    # app_monitor.sh for MIOT
    $SETPROP sys.app_monitor_delay 20
    local platform=`${GETPROP} persist.sys.cloud`
    if [ "$platform" = "miot" ]; then
        app_monitor.sh &
        log_monitor.sh &
    fi
}

#
# Self-checking current platform and to run programs.
#
run_xxxx()
{
    local platform=""

    #
    # Retry 4 times to get platform type.
    #
    for i in 1 1 2 0; do
        platform=`${GETPROP} persist.sys.cloud`
        if [ ! -n "$platform" ]; then sleep $i; else break; fi
    done

    #
    # Use default type if can't get type from the property server.
    #
    if [ ! -n "$platform" ]; then
        platform=$DEFAULT_PLATFORM
        ${SETPROP} persist.sys.cloud "$DEFAULT_PLATFORM"
    fi

    green_echo "Platform: $platform"

    if [ "$platform" = "aiot" ]; then run_aiot; return; fi

    if [ "$platform" = "miot" ]; then run_miot; return; fi
}

#
# Stop AIOT programs.
# Note: We can specifing some programs to keep alive
#       by use of format string: "x;x;x...".
#
# Flag: ha_driven        : d
#       ha_master        : m
#       ha_basis         : b
#       ha_agent         : a
#       property_service : p
#       zigbee_agent     : z
#
# For example: keep ha_basis and ha_master alive: stop_aiot "b;m"
#
stop_aiot()
{
    red_echo "AIOT is not supported yet!"
}

#
# Stop MIOT programs.
# Note: We can specifing some programs to keep alive
#       by use of format string: "x;x;x...".
#
# Flag:
#       miio_agent
#       mha_basis
#       mZ3GatewayHost_MQTT
#       mzigbee_agent
#       miio_client
#       mha_master
#       mijia_automation
#       miio_bt
#       central_lite
#       ot_service
#       http_service
#       matter_gateway_service
#       translation_service
#
# For example: keep mha_basis and mha_master alive: stop_miot "mha_basis;mha_master"
#
stop_miot()
{
    local b=0; local m=0; local h=0; local g=0
    local c=0; local z=0; local a=0; local p=0
    local l=0; local t=0; local i=0; local n=0
    local mo=0; local mh=0; local mg=0; local mt=0
    echo "stop miot"

    match_substring "$1" "b"; b=$?
    match_substring "$1" "m"; m=$?
    match_substring "$1" "h"; h=$?
    match_substring "$1" "g"; g=$?
    match_substring "$1" "c"; c=$?
    match_substring "$1" "z"; z=$?
    match_substring "$1" "a"; a=$?
    match_substring "$1" "p"; p=$?
    match_substring "$1" "t"; t=$?
    match_substring "$1" "i"; i=$?
    match_substring "$1" "n"; n=$?
    match_substring "$1" "mo"; mo=$?
    match_substring "$1" "mh"; mh=$?
    match_substring "$1" "mg"; mg=$?
    match_substring "$1" "mt"; mt=$?

    # Stop monitor.
    killall -9 app_monitor.sh
    killall -9 log_monitor.sh

    #
    # Send a signal to programs.
    #
    killall -9 miio_client_helper_nomqtt.sh
    if [ $a -eq 0 ]; then killall mijia_automation ;fi
    if [ $h -eq 0 ]; then killall homekitserver    ;fi
    if [ $m -eq 0 ]; then killall mha_master       ;fi
    if [ $c -eq 0 ]; then killall miio_client      ;fi
    if [ $b -eq 0 ]; then killall mha_basis        ;fi
    if [ $p -eq 0 ]; then killall property_service ;fi
    if [ $g -eq 0 ]; then killall miio_agent       ;fi
    if [ $z -eq 0 ]; then killall mzigbee_agent    ;fi
    if [ $l -eq 0 ]; then killall mZ3GatewayHost_MQTT ;fi
    if [ $t -eq 0 ]; then killall miio_bt          ;fi
    if [ $n -eq 0 ]; then killall central_lite     ;fi
    if [ $mo -eq 0 ]; then killall ot_service      ;fi
    if [ $mh -eq 0 ]; then killall http_service    ;fi
    if [ $mg -eq 0 ]; then killall matter_gateway_service ;fi
    if [ $mt -eq 0 ]; then killall translation_service    ;fi

    # P3 programs.
    if [ "$model" = "AC_P3" ]; then killall mha_ir; fi

    sleep 1

    #
    # Force to kill programs.
    #
    if [ $a -eq 0 ]; then killall -9 mijia_automation    ;fi
    if [ $h -eq 0 ]; then killall -9 homekitserver       ;fi
    if [ $m -eq 0 ]; then killall -9 mha_master          ;fi
    if [ $c -eq 0 ]; then killall -9 miio_client         ;fi
    if [ $b -eq 0 ]; then killall -9 mha_basis           ;fi
    if [ $p -eq 0 ]; then killall -9 property_service    ;fi
    if [ $g -eq 0 ]; then killall -9 miio_agent          ;fi
    if [ $z -eq 0 ]; then killall -9 mzigbee_agent       ;fi
    if [ $l -eq 0 ]; then killall -9 mZ3GatewayHost_MQTT ;fi
    if [ $t -eq 0 ]; then killall -9 miio_bt             ;fi
    if [ $n -eq 0 ]; then killall -9 central_lite        ;fi
    if [ $mo -eq 0 ]; then killall -9 ot_service      ;fi
    if [ $mh -eq 0 ]; then killall -9 http_service    ;fi
    if [ $mg -eq 0 ]; then killall -9 matter_gateway_service ;fi
    if [ $mt -eq 0 ]; then killall -9 translation_service    ;fi

    # P3 programs.
    if [ "$model" = "AC_P3" ];then killall -9 mha_ir; fi
}

force_stop_unlimited()
{
    killall -9 app_monitor.sh
    killall -9 property_service

    # AIOT
    sleep 2

    # MIOT
    killall -9 miio_agent
    killall -9 mha_basis
    killall -9 mZ3GatewayHost_MQTT
    killall -9 mzigbee_agent
    killall -9 miio_client
    killall -9 mha_master
    killall -9 mijia_automation
    killall -9 miio_bt
    killall -9 central_lite
    killall -9 ot_service
    killall -9 http_service
    killall -9 matter_gateway_service
    killall -9 translation_service
    killall -9 miio_client_helper_nomqtt.sh
}

#
# Clean user data and then restore factory data.
#
factory_clean()
{
    green_echo "Factory reset."

    killall property_service

    sleep 0.1

    ubifs_format.sh 1 /data

    mkdir -p /data/storage

    factory_data restore

    sync

    echo 3 >/proc/sys/vm/drop_caches

    property_service -i /etc/build.prop -p /data/storage/prop.dat -b

    # Waitting for property_service to ready.
    wait_property_svr_ok
}

switch2_prepare()
{
    local from="$1"
    local to="$2"

    green_echo "Switch platform from $from to $to"

    # Backup data, and restores after switch.
    zigbee_ver_=`${GETPROP} persist.sys.zb_ver`
    zigbee_rpa_=`${GETPROP} persist.sys.zb_pa`
    hk_uuid_=`${GETPROP} persist.sys.hap_token_uuid`
    hk_token_=`${GETPROP} persist.sys.hap_token_key`

    if [ "$from" = "aiot" ]; then stop_aiot; return; fi

    if [ "$from" = "miot" ]; then stop_miot; return; fi
}

#
# Switch to platform: AIOT.
#
switch2_aiot()
{
    # Prepare: stop current program.
    switch2_prepare "$1" "aiot"

    # Factory reset to clean user data.
    factory_clean

    # Update the platform type[aiot] into factory database.
    ${SETPROP} persist.sys.cloud aiot

    # Restore data.
    ${SETPROP} persist.sys.zb_ver "$zigbee_ver_"
    ${SETPROP} persist.sys.zb_pa  "$zigbee_rpa_"
    ${SETPROP} persist.sys.hap_token_uuid "$hk_uuid_"
    ${SETPROP} persist.sys.hap_token_key "$hk_token_"

    # Run AIOT programs.
    run_aiot
}

#
# Switch to platform: MIOT.
#
switch2_miot()
{
    switch2_prepare "$1" "miot"

    # Factory reset to clean user data.
    factory_clean

    # Update the platform type[miot] into factory database.
    ${SETPROP} persist.sys.cloud miot

    # Restore data.
    ${SETPROP} persist.sys.zb_ver "$zigbee_ver_"
    ${SETPROP} persist.sys.zb_pa  "$zigbee_rpa_"
    ${SETPROP} persist.sys.hap_token_uuid "$hk_uuid_"
    ${SETPROP} persist.sys.hap_token_key "$hk_token_"

    # Run MIOT programs.
    run_miot
}

#
# Self-checking current platform and switch to another platform.
#
switch2_xxxx()
{
    local platform="$1"

    red_echo "Cloud switchover is not supported!"

    #green_echo "Current platform: $platform"

    #if [ "$platform" = "aiot" ]; then switch2_miot "$platform"; return; fi

    #if [ "$platform" = "miot" ]; then switch2_aiot "$platform"; return; fi
}

factory_prepare()
{
    FACTORY_RESTTING=1

    # Backup data, and restores after factory reset.
    vvplatform_="$1"
    zigbee_ver_=`${GETPROP} persist.sys.zb_ver`
    zigbee_rpa_=`${GETPROP} persist.sys.zb_pa`
    hk_uuid_=`${GETPROP} persist.sys.hap_token_uuid`
    hk_token_=`${GETPROP} persist.sys.hap_token_key`


    if [ "$vvplatform_" = "aiot" ]; then stop_aiot ; return; fi

    if [ "$vvplatform_" = "miot" ]; then stop_miot ; return; fi
}

#
# Recovery some data and programs.
#
factory_recovery()
{
#   ${SETPROP} persist.sys.cloud  "$vvplatform_"
    ${SETPROP} persist.sys.zb_ver "$zigbee_ver_"
    ${SETPROP} persist.sys.zb_pa  "$zigbee_rpa_"
    ${SETPROP} persist.sys.hap_token_uuid "$hk_uuid_"
    ${SETPROP} persist.sys.hap_token_key "$hk_token_"
    ${SETPROP} sys.hap_disable

    sync

    WIFI_START_PARAMS="FACRST"
    cur_cloud=`${GETPROP} persist.sys.cloud`
    if [ "$cur_cloud" = "aiot" ]; then run_aiot "r"; return; fi

    if [ "$cur_cloud" = "miot" ]; then run_miot "r"; return; fi
}

#
# Recovery some data and programs.
#

factory_reset()
{
    local platform=`${GETPROP} persist.sys.cloud`

    touch /res/factory_resetting

    sync

    # Prepare, stop some programs, save some data.
    factory_prepare "$platform"

    # Clean user data.
    factory_clean

    # Recovery.
    factory_recovery

    # Recovery specially.
    rm -f /res/factory_resetting
    sync

    green_echo "factory reset done!"
}

#
# Entry factory test mode.
# This function will causing system to reboot.
#
factory_test()
{
    green_echo "Entry factory test."

    force_stop_unlimited

    factory_clean

    ${SETPROP} persist.sys.factory_result false
    echo "key_enter_fac_"`date` >> /res/fac_key.log

    sync;sync;sync;sleep 1; reboot
}

#
# Prepare for update.
# Return value 1 : failed.
# Return value 0 : ok.
#
update_prepare()
{
    ota_dir_="/tmp/ota_dir"
    coor_dir_="/data/ota-files"
    fws_dir_="/data/ota_dir"

    # Clean old firmware directory.
    if [ -d $fws_dir_ ]; then rm $fws_dir_ -rf; fi
    if [ -d $coor_dir_ ]; then rm $coor_dir_ -rf; fi
    if [ -d $ota_dir_ ]; then rm $ota_dir_ -rf; fi

    # Clean log files.
    rm /tmp/bmlog.txt* -f
    rm /tmp/zblog.txt* -f
    rm /tmp/aulog.txt* -f

    killall -9 app_monitor.sh
    echo 3 >/proc/sys/vm/drop_caches; sleep 1

    dfu_pkg_="$1"


    firmwares_="$fws_dir_/lumi_fw.tar"

    kernel_bin_="$ota_dir_/kernel"
    rootfs_bin_="$ota_dir_/rootfs.sqfs"

    irctrl_bin_="$ota_dir_/IRController.bin"
    ble_bl_bin_="$ota_dir_/bootloader.gbl"
    ble_app_bin_="$ota_dir_/full.gbl"


    ble_bl_bin_bk_="/data/bootloader.gbl"
    ble_app_bin_bk_="/data/full.gbl"

    local dfusize=`du "$dfu_pkg_" | awk '{print $1}'`
    local memfree=`cat /proc/meminfo | grep MemFree | tr -cd "[0-9]"`
    local romfree=`df | grep data  | awk '{print $4}'`

    dfusize_=`convert_str2int "$dfusize"`
    memfree_=`convert_str2int "$memfree"`
    romfree_=`convert_str2int "$romfree"`

    green_echo "Original OTA package : $dfu_pkg_"
    green_echo "Unpack path          : $ota_dir_"
    green_echo "Firmware path        : $fws_dir_"
    green_echo "OTA packages size(kb) : $dfusize_"
    green_echo "Available ROM size(kb): $romfree_"
    green_echo "Available RAM size(kb): $memfree_"

    # Check memory space.
    # Failed to get var if romfree_/memfree_ equal zero.
    if [[ $romfree_ -lt $dfusize_ ]] || [[ $memfree_ -lt $dfusize_ ]]; then
        red_echo "Not enough storage available!"
        return 1
    fi

    mkdir -p $fws_dir_ $coor_dir_ $ota_dir_

    return 0
}

update_unpack()
{
    local platform="$1"

    local path="$2"
    local sign="$3"

    # AIOT
    if [ "$platform" = "aiot" ]; then
        fw_unpack "$path" "$sign"
        if [ -f "$firmwares_" ]; then return 0; fi
    fi

    # MIOT
    if [ "$platform" = "miot" ]; then
        fw_miot_unpack "$path" "$sign"

        local result=`${GETPROP} sys.dfu_progress`
        if [ $result -ge 0 ]; then return 0; fi
    fi

    return 1
}

update_clean()
{
    rm -rf "$dfu_pkg_" "$fws_dir_" "$ota_dir_"
    sync;sync;sync; sleep 1
}

#
# Check update status was block or not.
# return value 1: true.
# return value 0: false.
#
update_block()
{
    local result=`${GETPROP} sys.dfu_progress`
    if [ "$result" = "-1" ]; then return 1; fi

    return 0
}

confirm_coor()
{
    zigbee_msnger get_zgb_ver
    sleep 0.1
    local index2=`${GETPROP} sys.coor_update`
    if [ "$index2" != "true" ]; then
        return 1
    else
        # check ver
        # local ver=`${GETPROP} persist.sys.zb_ver`
        # if [ "$g_zbcoor_need_ver" = "$ver" ];then
        #     echo "same ver"
        #     return 0
        # else
        #     red_echo "diff ver" 
        #     echo "need ver:$g_zbcoor_need_ver,curr ver:$ver"
        # fi
        return 0
    fi

    return 1
}



update_before_start()
{
    local platform="$1"

    # Untar.
    if [ "$platform" = "aiot" ]; then
        echo 3 >/proc/sys/vm/drop_caches
        tar -xvf "$firmwares_" -C "$ota_dir_"
    fi
}


get_kernel_partitions(){

    /etc/fw_printenv | grep bootcmd | awk '{print $4}'
}

get_rootfs_partitions(){

    cat /proc/cmdline | grep mtdblock7
}
set_kernel_partitions(){
    
    if [ "$1" = "KERNEL" ];then
        /etc/fw_setenv bootcmd "nand read.e 0x22000000 KERNEL_BAK 0x500000; dcache on; bootlogo 0 0 0 0; bootm 0x22000000;nand read.e 0x22000000 KERNEL 0x500000; dcache on; bootm 0x22000000"
    else
        /etc/fw_setenv bootcmd "nand read.e 0x22000000 KERNEL 0x500000; dcache on; bootlogo 0 0 0 0; bootm 0x22000000;nand read.e 0x22000000 KERNEL_BAK 0x500000; dcache on; bootm 0x22000000"
    fi
}

set_rootfs_partitions(){
    
    if [ x"$1" != x ];then
        /etc/fw_setenv bootargs "root=/dev/mtdblock8 rootfstype=squashfs ro init=/linuxrc LX_MEM=0x7FE0000 mma_heap=mma_heap_name0,miu=0,sz=0x500000 cma=2M mmap_reserved=fb,miu=0,sz=0x300000,max_start_off=0x7C00000,max_end_off=0x7F00000 mtdparts=nand0:1664k@0x140000(BOOT0),1664k(BOOT1),256k(ENV),256k(ENV1),128k(KEY_CUST),5m(KERNEL),5m(KERNEL_BAK),16m(rootfs),16m(rootfs_bak),1m(factory),20m(RES),-(UBI)"
    else
        /etc/fw_setenv bootargs "root=/dev/mtdblock7 rootfstype=squashfs ro init=/linuxrc LX_MEM=0x7FE0000 mma_heap=mma_heap_name0,miu=0,sz=0x500000 cma=2M mmap_reserved=fb,miu=0,sz=0x300000,max_start_off=0x7C00000,max_end_off=0x7F00000 mtdparts=nand0:1664k@0x140000(BOOT0),1664k(BOOT1),256k(ENV),256k(ENV1),128k(KEY_CUST),5m(KERNEL),5m(KERNEL_BAK),16m(rootfs),16m(rootfs_bak),1m(factory),20m(RES),-(UBI)"
    fi
}


get_coor_file_ver()
{
    ver=`echo $1 | cut -d "_" -f 6`
    echo $ver
}


set_def_env(){
    echo "set default env"
    /etc/fw_setenv mtdparts 'mtdparts=nand0:1664k@0x140000(BOOT0),1664k(BOOT1),256k(ENV),256k(ENV1),128k(KEY_CUST),5m(KERNEL),5m(KERNEL_BAK),16m(rootfs),16m(rootfs_bak),1m(factory),20m(RES),-(UBI)'
    /etc/fw_setenv bootargs "root=/dev/mtdblock7 rootfstype=squashfs ro init=/linuxrc LX_MEM=0x7FE0000 mma_heap=mma_heap_name0,miu=0,sz=0x500000 cma=2M mmap_reserved=fb,miu=0,sz=0x300000,max_start_off=0x7C00000,max_end_off=0x7F00000 mtdparts=nand0:1664k@0x140000(BOOT0),1664k(BOOT1),256k(ENV),256k(ENV1),128k(KEY_CUST),5m(KERNEL),5m(KERNEL_BAK),16m(rootfs),16m(rootfs_bak),1m(factory),20m(RES),-(UBI)"
    /etc/fw_setenv bootcmd "nand read.e 0x22000000 KERNEL 0x500000; dcache on; bootlogo 0 0 0 0; bootm 0x22000000;nand read.e 0x22000000 KERNEL_BAK 0x500000; dcache on; bootm 0x22000000"
    
}



coordinator_ota()
{
    echo "RCP mode: stock coordinator OTA skipped"
    return 0
 # Update zigbee-coordinator firmware.
    echo "===Update zigbee-coordinator==="

    local zb_platform=MG21
    # local file_size=`ls $zbcoor_bin_  -al | awk '{print $5}'`

    zbcoor_bin_="/data/Network-Co-Processor.ota"

    local tmpfile=`find $ota_dir_ -name Network-Co-Processor*`
    local name=`basename $tmpfile`
    echo "tmpfile:$tmpfile"
    if [ ! -z $tmpfile ] && [ -f $tmpfile ]; then
        cp -fv $tmpfile $zbcoor_bin_
    fi
    ${SETPROP} sys.coor_update false
    # zbcoor_bin_bk_="/data/Network-Co-Processor.ota"

    if [ -z $zbcoor_bin_ ] || [ ! -f "$zbcoor_bin_" ]; then
        echo "no co_ota file"
        return 0
    fi

    local DFU_VER=`${GETPROP} persist.app.dfu_ver`
    local CLOUD_VER=`echo $DFU_VER | cut -d '.' -f 4`
    local LOCAL_VER=`${GETPROP} persist.sys.zb_ver`

    echo "cloud ver:$CLOUD_VER,local :$LOCAL_VER"

    if  [ "$CLOUD_VER" != "$LOCAL_VER" ]; then
        if [ -f "$zbcoor_bin_" ]; then
            # cp -f "$zbcoor_bin_" "$zbcoor_bin_bk_"
            for i in `seq 3`;do
                if [ ! `pgrep mZ3GatewayHost_MQTT` ];then
                    red_echo "zigbee_msnger not running, start it"
# RCP mode disabled:                     mZ3GatewayHost_MQTT -p /dev/ttyS1 -d /data/zigbee_host/ -r 'c' 2>&1 | logger -t "zigbee_host" &
                    sleep 1
                fi
                zigbee_msnger zgb_ota "$zbcoor_bin_"
                    echo "zigbee_msnger zgb_ota $zbcoor_bin_"
                for retry in `seq 28`
                do
                    sleep 1
                    # Check result
                    confirm_coor
                    var=$?
                    if [ $var -eq 0 ]; then break; fi
                done

                if [ $var -eq 0 ]; then 
                    break;
                else
                    red_echo "zigbee_msnger zgb_ota fail, retry $i"
                fi
            done
            # rm -f "$zbcoor_bin_bk_"
            if [ $var -ne 0 ]; then
                red_echo "coordinator ota fail"
                return 1
            fi

            rm $zbcoor_bin_
            sync

        fi
    else
        echo "same coordinator ver"
    fi


    return 0
}

ota_kernel()
{
    # Update kernel.
    echo "===Update kernel==="
    KERNEL_PARTITION=$(get_kernel_partitions)
    for cnt in `seq 4`
    do
    if [ -f "$kernel_bin_" ];then
        if [ "$KERNEL_PARTITION" = "KERNEL" ];then
            flash_erase /dev/mtd6 0 0
            /bin/nandwrite -p /dev/mtd6 $kernel_bin_; sync; sleep 0.4
            /bin/nanddump -s 0x0 -l 0x1 -f /tmp/kernel_head -p /dev/mtd6
            cat /tmp/kernel_head | awk -F ':' '{print $2}' >> /tmp/kernel_head0
        else
            flash_erase /dev/mtd5 0 0
            /bin/nandwrite -p /dev/mtd5 $kernel_bin_; sync; sleep 0.4
            /bin/nanddump -s 0x0 -l 0x1 -f /tmp/kernel_head -p /dev/mtd5
            cat /tmp/kernel_head | awk -F ':' '{print $2}' >> /tmp/kernel_head0
        fi

        hexdump -n 2048 -e '16/1 "%02x" "\n"' $kernel_bin_ >> /tmp/kernel_head1
        result=`diff -w /tmp/kernel_head0 /tmp/kernel_head1`
        rm -f /tmp/kernel_head0; rm -f /tmp/kernel_head1; rm -f /tmp/kernel_head
        if [ "$result" = "" ];then break; fi

   fi
   done
   if [ $cnt -eq 4 ];then return 1; fi
   return 0
}


ota_rootfs() {
    # Update rootfs.
    echo "===Update rootfs==="
    ROOTFS_PARTITION=$(get_rootfs_partitions)
    for cnt in $(seq 4); do
        if [ -f "$rootfs_bin_" ]; then
            local index=7
            if [ x"$ROOTFS_PARTITION" != x ]; then
                flash_erase /dev/mtd8 0 0
                /bin/nandwrite -p /dev/mtd8 $rootfs_bin_
                sync
                sleep 0.4
                /bin/nanddump -s 0x0 -l 0x1 --bb=dumpbad -f /tmp/rootfs_head -p /dev/mtd8
                cat /tmp/rootfs_head | awk -F ':' '{print $2}' >>/tmp/rootfs_head0
                index=8
            else
                flash_erase /dev/mtd7 0 0
                /bin/nandwrite -p /dev/mtd7 $rootfs_bin_
                sync
                sleep 0.4
                /bin/nanddump -s 0x0 -l 0x1 --bb=dumpbad -f /tmp/rootfs_head -p /dev/mtd7
                cat /tmp/rootfs_head | awk -F ':' '{print $2}' >>/tmp/rootfs_head0
                index=7
            fi
            hexdump -n 2048 -e '16/1 "%02x" "\n"' $rootfs_bin_ >>/tmp/rootfs_head1
            result=$(diff -w /tmp/rootfs_head0 /tmp/rootfs_head1)

            if [ "$result" != "" ];then
                echo "check again"
                /bin/nanddump -s 0x0 -l 0x1 -f /tmp/rootfs_head -p /dev/mtd$index
                cat /tmp/rootfs_head | awk  -F ':' '{print $2}' >> /tmp/rootfs_head0
                result=$(diff -w /tmp/rootfs_head0 /tmp/rootfs_head1)
            fi

            rm -f /tmp/rootfs_head0
            rm -f /tmp/rootfs_head1
            rm -f /tmp/rootfs_head
            if [ "$result" = "" ]; then break; fi
        fi
    done

    if [ $cnt -eq 4 ]; then return 1; fi

    return 0
}

check_env()
{
    local err_crc=`/etc/fw_printenv 2>&1 | grep "Bad CRC"`
    if [ x"$err_crc" != x ];then
        red_echo "last env error,set default env"
        set_def_env
    else
        echo "env right" 
    fi
}

update_start()
{
    local platform="$1"
    local coor_bin_name=`echo $ota_dir_/*.ota | cut -d '/' -f 4` 

    check_env

    ${SETPROP} sys.dfu_progress 75

    ${SETPROP} sys.dfu_progress 80
    coordinator_ota

    if [ $? -eq 1 ];then
        echo "coordinator ota fail"
        return 1
    fi

    ${SETPROP} sys.dfu_progress 90

    ota_kernel
    if [ $? -eq 1 ];then
        echo "kernel ota fail"
        return 1
    fi

    ${SETPROP} sys.dfu_progress 95

    ota_rootfs

    if [ $? -eq 1 ];then
        echo "rootfs ota fail"
        return 1
    fi

    echo "===Update ALL Success==="

    return 0
}

update_failed()
{
    local platform="$1"
    local errmsg="$2"
    local clean="$3"

    green_echo "Update failed, reason: $errmsg"

    if [ "$clean" = "true" ]; then update_clean; fi

    if [ "$platform" = "miot" ]; then ${SETPROP} sys.dfu_progress -33005;
    else ${SETPROP} sys.dfu_progress -1; fi

    if [ ! $(pgrep -f app_monitor.sh) ]; then
        app_monitor.sh &
    fi

}

update_done()
{
    set_kernel_partitions "$KERNEL_PARTITION"
    set_rootfs_partitions "$ROOTFS_PARTITION"
    update_clean
    ${SETPROP} sys.dfu_progress 100
    sleep 7
    reboot
}

test_set_tags()
{
    local file="$1"
    local xtag="$2"

    if [ "$file" = "" ]; then green_echo "Error: file not found!"; return ;fi
    if [ "$xtag" = "" ]; then green_echo "Error: tag not found!"; return  ;fi

    set_tags "$file" "$xtag"
}

test_get_tags()
{
    local file="$1"

    if [ "$file" = "" ]; then green_echo "Error: file not found!"; return ;fi

    get_tags "$file"
}

test_post_init()
{
    local path="/data/scripts"
    local script="$path/post_init.sh"

    local platform=`${GETPROP} persist.sys.cloud`

    if [ ! -d "$path" ]; then mkdir $path; fi

    # AIOT
    if [ "$platform" = "aiot" ]; then
cat <<EOF > $script
#!/bin/sh

mdnsd
mosquitto -d

#
# P3 must to run this process.
#
#power_init

ha_agent -D

zigbee_agent -f /etc/zigbeeAgent.conf >/dev/null 2>&1 &

ha_basis &

#
# P3 run this process.
#
#ha_master -H -r /lib/libha_ir.so -a /lib/libha_auto.so &
ha_master -S -H -a /lib/libha_auto.so -g /lib/libha_energy.so &

# RCP mode disabled: Z3GatewayHost_MQTT -p /dev/ttyS1 -d /data/ >/dev/null 2>&1 &
ha_driven > /dev/null 2>&1 &
EOF
    fi

    # MIOT
    if [ "$platform" = "miot" ]; then
cat <<EOF > $script
#!/bin/sh

mdnsd
mosquitto -d

#
# P3 must to run this process.
#
#power_init

[ -d /data/miio ] || mkdir -p /data/miio
[ -d /data/zoneinfo ] || mkdir -p /data/zoneinfo

miio_agent -l0 -D; sleep 1
# RCP mode disabled: mzigbee_agent -f /etc/mzigbeeAgent.conf >/dev/null 2>&1 &
mha_basis > /dev/null 2>&1 &

miio_client_helper_nomqtt.sh &
sleep 0.2
miio_client -l4 -d /data/miio/ -n128 -o DISABLE_PSM -D
mha_master > /dev/null 2>&1 &
mijia_automation -d /data/miio 2>&1 > /dev/null &

homekitserver >/dev/null 2>&1 &

#
# P3 must to run this process.
#
#mha_ir -r /lib/libha_ir.so >/dev/null 2>&1 &

sleep 3
wifi_start.sh INIT

cp="\`${GETPROP} persist.app.cloud_provisioned\`"
hp="\`${GETPROP} persist.app.hap_provisioned\`"
ka="\`${GETPROP} persist.app.hap_keepalive\`"
if [ ! "\$cp" = "true" ] && [ ! "\$hp" = "true" ] && [ ! "\$ka" = "true" ];
then
    wifi_start.sh AP
else
    wifi_start.sh STA &
fi

EOF
    fi

    chmod +x $script
}

test_set_hostname()
{
    local name="$1"
    if [ "$name" = "" ]; then green_echo "Error: hostname not found!"; return; fi

    green_echo "hostname: $name"

    hostname "$name"
}

test_build_hostname()
{
    model="$1"
    green_echo "model:$model"

    set_hostname
}

test_user_behavior()
{
    # Enable Uart.
    /bin/riu_w 101e 53 3012

    # Start telnet.
    local running=`pgrep telnetd`
    if [ "$running" = "" ]; then telnetd; fi
}

#
# Document helper.
#
helper()
{
    local cmd="$1"

    case $cmd in
        -r) usage_runner   ;;

        -s) usage_switcher ;;

        -f) usage_factory  ;;

        -u) usage_updater  ;;

        -t) usage_tester   ;;

         *) usage_helper   ;;
    esac

    return 0
}

#
# Run user programs.
#
runner()
{
    local opt="$1"

    run_prepare

    case $opt in
        -a) run_aiot ;;

        -m) run_miot ;;

         *) run_xxxx ;;
    esac

    return 0
}

#
# Switch platform.
#
switcher()
{
    echo "no support switcher"

    return 1

    local opt="$1"

    local platform=`${GETPROP} persist.sys.cloud`

    case $opt in
        -a) switch2_aiot "$platform" ;;

        -m) switch2_miot "$platform" ;;

         *) switch2_xxxx "$platform" ;;
    esac

    return 0
}

#
# Factory operations.
#
factory()
{
    local opt="$1"

    case $opt in
        -r) factory_reset ;;

        -m) factory_test  ;;

         *) green_echo "Lost params." ;;
    esac

    return 0
}

#
# Update firmware.
#
updater()
{
    if [ $# -lt 3 ]; then green_echo "Lost params."; return 1; fi

    local sign="0"
    local path="$3"

    # Check file existed or not.
    if [ ! -f "$path" ]; then update_failed "x" "$path not found!"; return 1; fi

    # Need check sign?
    if [ "$2" = "-s" ]; then sign="1"; fi

    local platform=`${GETPROP} persist.sys.cloud`
    if [ "$platform" = "" ]; then platform=$DEFAULT_PLATFORM; fi

    green_echo "platform: $platform, path: $path, sign: $sign"

    # Prepare...
    update_prepare "$path"
    if [ $? -ne 0 ]; then
        update_failed "$platform" "Not enough storage available!";
        return 1
    fi

    # Unpack DFU package and check it.
    update_unpack "$platform" "$path" "$sign"
    if [ $? -ne 0 ]; then
        update_failed "$platform" "unpack failed!" "true"
        return 1
    fi

    # Remove original DFU package to release memory.
    rm -rf "$path"

    update_before_start "$platform"

    update_start "$platform"
    if [ $? -eq 0 ]; then update_done;
    else update_failed "$platform" "OTA failed!" "true"; fi

    return 0
}

#
# Tester.
#
tester()
{
    local opt="$2"

    case $opt in
        -a) test_set_tags "$3" "$4" ;;

        -b) test_get_tags "$3"; green_echo "$?" ;;

        -c) convert_str2int "$3" ;;

        -d) stop_aiot ;;

        -e) stop_miot ;;

        -f) test_post_init ;;

        -g) test_set_hostname "$3" ;;

        -h) test_build_hostname "$3" ;;

        -i) /bin/riu_w 101e 53 3010;;

        -j) /bin/riu_w 101e 53 3012;;

        -k) test_user_behavior $* ;;

         *) green_echo "Lost params." ;;
    esac

    return 0
}

#
# Set hostname.
#
set_hostname()
{
    local suffix=`${GETPROP} persist.sys.wlan_mac | cut -b 13-14,16-17 | tr '[a-f]' '[A-F]'`
    if [ "$suffix" = "" ]; then suffix="0000"; fi

    test_set_hostname "Mijia_Hub_V2-$suffix"
}

#
# Sometimes, we need to compatible from old version to newer one.
#
compatible()
{
    get_tags "$REVISION_FILE"; local pre_revision="$?"

    green_echo "pre-revision: $pre_revision"

    case $pre_revision in
        0) green_echo "remove /data/lumi_fw"; rm -rf /data/lumi_fw ;;
        1) green_echo "remove /data/lumi_fw"; rm -rf /data/lumi_fw ;;

        *) green_echo "" ;;
    esac

    # Save newest revision into file.
    set_tags "$REVISION_FILE" "$REVISION"

    $(type getprop 2>&1 > /dev/null)  && [ $? -eq 0 ] && GETPROP=getprop || GETPROP=${GETPROP}
    $(type setprop 2>&1 > /dev/null)  && [ $? -eq 0 ] && SETPROP=setprop || SETPROP=${SETPROP}
}

#
# Get product model.
#
info_model()
{
    # Try: Get by attribute: persist.sys.model.
    for i in 1 2 1 0; do
        local userattr=`${GETPROP} persist.sys.model`
        if [ ! -n "$userattr" ]; then sleep $i; continue; fi

        if [ ! -f "$MODEL_FILE" ]; then set_tags "$MODEL_FILE" "$userattr"; fi

        echo "$userattr"; return
    done

    # Try: Get from file.
    if [ -f "$MODEL_FILE" ]; then local fileattr=`cat $MODEL_FILE`; echo "$fileattr"; return; fi

    # Try: Get by attribute: ro.sys.model.
    local sysattr=`${GETPROP} ro.sys.model`; echo "$sysattr"
}

check_zigbee_ic()
{
    ZIGBEE_IC="MG21"
    return
    local zb_platform=`${GETPROP} persist.sys.zb_chip`
    if [ x"$zb_platform" = x ];then
        # gpio_set.sh 43 1
        # gpio_set.sh 44 1
        # sleep 0.2
        # gpio_set.sh 44 0
        # sleep 0.2

        for i in `seq 4`;do
            local ismg21=`get_zbic | grep MG21`

            if [ x"$ismg21" != x ];then
                ZIGBEE_IC=MG21
                ${SETPROP} persist.sys.zb_chip "0021"
                green_echo "zigbee ic is mg21"
                break
            else
                green_echo "zigbee ic is p7"
            fi
            sleep 0.1
        done

    else
        if [ "$zb_platform" = "$CC2652P1" ] || [ "$zb_platform" = "$CC2652P7" ] || [ "$zb_platform" = "$CC1352P7" ]; then 
            ZIGBEE_IC="Ti2652"
        else
            ZIGBEE_IC="MG21"
        fi
    fi

}

config_mac_address()
{
    local lan_mac=$(${GETPROP} persist.sys.lan_mac)
    local lan_name=$(${GETPROP} persist.sys.lan_name)
    local wlan_mac=$(${GETPROP} persist.sys.wlan_mac)
    local wlan_name=$(${GETPROP} persist.sys.wlan_name)

    if [ "x$lan_mac" != "x" -a "x$lan_name" != "x" ]; then
        ifconfig $lan_name hw ether $lan_mac
    fi

    if [ "x$wlan_mac" != "x" -a "x$wlan_name" != "x" ]; then
        ifconfig $wlan_name hw ether $wlan_mac
    fi
}

#
# Initial params.
#
initial()
{
    wait_property_svr_ok
    config_mac_address
    check_zigbee_ic

    echo 3 > /proc/sys/kernel/printk

    local exit_flag=1

    # Is another script running?
    for i in 2 3 1 0; do
        local info=`ps`
        local this_num=`echo "$info" | grep "$1" | wc -l`

        if [ $this_num -le 1 ]; then exit_flag=0; break; fi

        sleep $i # Waitting...
    done

    if [ $exit_flag -ne 0 ]; then exit 1; fi

    green_echo "$1 revision: $REVISION"

    # Compatible by revision.
    compatible

    # Set ipv4 local reserved ports.
    echo "1883,54322" > /proc/sys/net/ipv4/ip_local_reserved_ports
    local product=`${GETPROP} ro.sys.product`

    model="$(info_model)"

    set_hostname

    if [ -e /res/factory_resetting ]; then
        red_echo "Unfinished factory_reset, factory_clean again!!!"
        factory_clean
        rm /res/factory_resetting
        #hap_token_recovery
    fi

    sync

    green_echo "type: $product, model: $model"
}

#
# Main function.
#
main()
{
    initial ${0##*/}

    local option="$1"

    case $option in
        -h) local cmd="$2"; helper   $cmd ;;

        -r) local opt="$2"; runner   $opt ;;

        -s) local opt="$2"; switcher $opt ;;

        -f) local opt="$2"; factory  $opt ;;

        -u) updater $* ;;

        -t) tester  $* ;;

         *) green_echo ""
            green_echo "Usage: $0 [option] [params]."
            green_echo "  option: $OPTIONS"
            green_echo "  params: params list."
            return 1
            ;;
    esac

    return $?
}

#
# Run script.
#
main $*; exit $? 
