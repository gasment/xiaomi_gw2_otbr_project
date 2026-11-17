#!/bin/sh
#
# @file    app_monitor.sh
# @brief   Here is a monitor to ensure other programs work properly,
#          in addition, if we want the app_monitor don't to check in
#          a period, just to set a property: sys.app_monitor_delay.
#          For example, delay 60 seconds to check:
#          $SETPROP sys.app_monitor_delay 60
#
# @author  Michael (huiwang.zhu@aqara.com)
#
# Copyright (c) 2020~2021 ShenZhen Lumiunited Technology Co., Ltd.
# All rights reserved.
#

REVISION="1.1.4"

#
# Cloud name, support list: miot.
#
CLOUD="miot"

#
# Product model, support list:
#

MODEL=""


#
# Period: how many seconds to check.
#
PERIOD=5

#
# Enable debug, 0/1.
#
DEBUG=0
LOGDBG=0


#
# File to store logs
#
LOGFILE=/var/log/app_monitor.log

#
# Max log size 1024 * 1024
#
MAX_LOG_SIZE=1048576

#
# Monitor log count
#
MONITOR_LOG_COUNT=1

#
# Monitor log period seconds
# Default:3600
#
MONITOR_LOG_PERIOD=3600

#
# Map of the AIoT-process and handler: <name,handler>.
#
# name    : process name.
# handler : when the state reset, this function should be calls.
#
# note: We agreed the return value of the handler must be 0/1, and
#       1 is to mean can't continue checking other programs is still
#       alived or not, 0 is opposite.
#
aiot_map=""

#
# Map of the MIoT-process and handler: <name,handler>.
#
# name    : process name.
# handler : when the state reset, this function should be calls.
#
# note: We agreed the return value of the handler must be 0/1, and
#       1 is to mean can't continue checking other programs is still
#       alived or not in this period, 0 is opposite.
#
miot_map="                                       \
miio_agent          handler_miio_agent_leaved    \
mosquitto           handler_mosquitto_leaved     \
mha_basis           handler_mha_basis_leaved     \
helper_nomqtt.sh    handler_miio_helper_leaved   \
miio_client         handler_miio_client_leaved   \
mha_master          handler_mha_master_leaved    \
mijia_automation    handler_mijia_auto_leaved    \
miio_bt             handler_miio_bt_leaved       \
"

GETPROP=agetprop
SETPROP=asetprop

compat()
{
    $(type getprop 2>&1 > /dev/null)  && [ $? -eq 0 ] && GETPROP=getprop || GETPROP=agetprop
    $(type setprop 2>&1 > /dev/null)  && [ $? -eq 0 ] && SETPROP=setprop || SETPROP=asetprop
}

#
# Show green content, in the same way to use as echo.
#
green_echo()
{
    if [ $DEBUG -eq 0 ]; then return; fi

    local time="$(date +%Y-%m-%d_%H:%M:%S)"
    local fmt="[$time]:"

    GREEN="\033[0;32m"; BLACK="\033[0m"
    if [ "$1" = "-n" ]; then echo -en $GREEN$fmt$2$BLACK; else echo -e $GREEN$fmt$1$BLACK; fi

    if [ -f $LOGFILE ]; then
        if [ "$1" = "-n" ]; then echo -en $fmt$2 >> $LOGFILE; else echo -e $fmt$1 >> $LOGFILE; fi
    fi
}

#
# Show red content, in the same way to use as echo.
#
red_echo()
{
    local time="$(date +%Y-%m-%d_%H:%M:%S)"
    local fmt="[$time]:"
    RED="\033[0;31m"; BLACK="\033[0m"
    if [ "$1" = "-n" ]; then echo -en $RED$fmt$2$BLACK; else echo -e $RED$fmt$1$BLACK; fi

    if [ -f $LOGFILE ]; then
        if [ "$1" = "-n" ]; then echo -en $fmt$2 >> $LOGFILE; else echo -e $fmt$1 >> $LOGFILE; fi
    fi
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
        *$substr[[:space:]]*) return 1 ;;
        *)                    return 0 ;;
    esac
}

handler_mZ3GatewayHost_MQTT_leaved()
{
    return 0 # RCP mode: do not restart stock Zigbee services
    red_echo "mZ3GatewayHost_MQTT leaved!"

    if [ $LOGDBG -eq 0 ]; then
        mZ3GatewayHost_MQTT -p /dev/ttyS1 -d /data/zigbee_host/ -r 'c' 2>&1 | logger -t "zigbee_host" &
    else
        mZ3GatewayHost_MQTT -p /dev/ttyS1 -d /data/zigbee_host/ -r 'c'  >> /tmp/zblog.txt 2>&1 &
    fi

    return 0
}

handler_central_lite_leaved()
{
    local cloud_provisioned="`$GETPROP persist.app.cloud_provisioned`"
    if [ "$cloud_provisioned" != "true" ]; then return 0; fi

    red_echo "central_lite leaved!"
    local miio_did="$($GETPROP persist.sys.miio_did)"
    mkdir -p /data/central_lite
    central_lite -d $miio_did -p /data/central_lite > /dev/null 2>&1 &

    return 0
}

handler_ot_service_leaved()
{
    red_echo "ot_service leaved!"
    ot_service > /dev/null 2>&1 &
    return 0
}

handler_http_service_leaved()
{
    red_echo "http_service leaved!"
    http_service > /dev/null 2>&1 &
    return 0
}

handler_matter_gateway_service_leaved()
{
    red_echo "matter_gateway_service leaved!"
    matter_gateway_service -l info -f syslog -c /etc -d > /dev/null 2>&1 &
    return 0;
}

handler_translation_service_leaved()
{
    red_echo "translation_service leaved!"
    mkdir -p /data/matter
    translation_service --model /data/matter/translation/specv3_models --mapping-table /data/matter/translation/resources_dict > /dev/null 2>&1 &
    return 0;
}


handler_miio_bt_leaved()
{
    red_echo "miio_bt leaved!"

    local pid_arg="$($GETPROP sys.miio_pid)"

    if [ "x$pid_arg" != "x" ]; then
        pid_arg="-p $pid_arg"
    fi

    miio_bt -l3 $pid_arg -b 2>&1 > /dev/null &

    return 0
}

#
# Handler event: miio_agent leaved.
#
# warning: return 0, see note of miot_map.
# note: restart miio_agent.
#
handler_miio_agent_leaved()
{
    red_echo "miio_agent leaved!"

    miio_agent -l0 -D

    return 0
}

#
# Handler event: mosquitto leaved.
#
# warning: return 0, see note of miot_map.
# note: restart mosquitto.
#
handler_mosquitto_leaved()
{
    red_echo "mosquitto leaved!"

    mosquitto -d

    return 0
}

#
# Handler event: mha_basis leaved.
#
# warning: return 0, see note of miot_map.
# note: restart mha_basis.
#
handler_mha_basis_leaved()
{
    red_echo "mha_basis leaved!"

    mha_basis > /dev/null 2>&1 &

    # Waitting for other process to ready.
    wifi_start.sh INIT

    cp="`$GETPROP persist.app.cloud_provisioned`"
    hp="`$GETPROP persist.app.hap_provisioned`"
    ka="`$GETPROP persist.app.hap_keepalive`"
    if [ ! "$cp" = "true" ] && [ ! "$hp" = "true" ] && [ ! "$ka" = "true" ];
    then
        wifi_start.sh AP
    else
        wifi_start.sh STA &
    fi

    return 0
}

#
# Handler event: mzigbee_agent leaved.
#
# warning: return 0, see note of miot_map.
# note: restart mzigbee_agent.
#
handler_mzigbee_agent_leaved()
{
    return 0 # RCP mode: do not restart stock Zigbee services
    red_echo "mzigbee_agent leaved!"

    mzigbee_agent -f /etc/mzigbeeAgent.conf 2>&1 | logger -t "zigbee_agent" &

    return 0
}

#
# Handler event: miio_client_helper leaved.
#
# warning: return 0, see note of miot_map.
# note: restart miio_client_helper_nomqtt.sh.
#
handler_miio_helper_leaved()
{
    red_echo "miio_client_helper leaved!"

    miio_client_helper_nomqtt.sh 2>&1 > /dev/console &

    return 0
}

#
# Handler event: miio_client leaved.
#
# warning: return 0, see note of miot_map.
# note: restart miio_client.
#
handler_miio_client_leaved()
{
    red_echo "miio_client leaved!"

    miio_client -l1 -d /data/miio/ -n 128 2>&1 > /dev/null -D

    return 0
}

#
# Handler event: mha_master leaved.
#
# warning: return 0, see note of miot_map.
# note: restart mha_master.
#
handler_mha_master_leaved()
{
    red_echo "mha_master leaved!"

    mha_master --log-level 6 --background

    return 0
}

#
# Handler event: mijia_automation leaved.
#
# warning: return 0, see note of miot_map.
# note: restart mijia_automation.
#
handler_mijia_auto_leaved()
{
    red_echo "mijia_automation leaved!"

    mijia_automation -d /data/miio >/dev/null 2>&1 | logger -t "mijia_automation" &

    return 0
}

#
# Initial params.
#
initial()
{
    compat

    MODEL="$($GETPROP persist.sys.model)"
    [ "x$MODEL" = "x" ] && MODEL="$($GETPROP ro.sys.model)"

    # counter for ticker
    ticker_count=0

    DEBUG_LOG=`$GETPROP persist.app.debug_log`

    if [ "$DEBUG_LOG" == "true" ]; then LOGDBG=1
    else LOGDBG=0; fi

    if [ ! -f "$LOGFILE" ]; then
        touch $LOGFILE
    fi

    #
    # Get cloud type.
    #
    while [ 1 ]; do
        CLOUD=`$GETPROP persist.sys.cloud`
        if [ ! -n "$CLOUD" ]; then sleep $PERIOD; else break; fi
    done

    if [ "$MODEL" = "lumi.gateway.mcn001" ]; then
        miot_map="${miot_map} central_lite handler_central_lite_leaved"
    fi

    #
    # MIOT_MATTER
    #
    local matter_supported="$(${GETPROP} persist.sys.matter_supported)"
    if [ "$MODEL" = "lumi.gateway.mgl001" -o "$matter_supported" = "true" ]; then
        miot_map="${miot_map} ot_service handler_ot_service_leaved"
        miot_map="${miot_map} http_service handler_http_service_leaved"
        miot_map="${miot_map} matter_gateway_service handler_matter_gateway_service_leaved"
        miot_map="${miot_map} translation_service handler_translation_service_leaved"
    fi
}



#
# Check log file size and limit it
#
limit_log_size()
{
    if [ ! -f "$LOGFILE" ]; then
        touch $LOGFILE
    fi

    local filesize=$(ls -l $LOGFILE | awk '{ print $5 }')

    if [ $filesize -gt $MAX_LOG_SIZE]; then
        cp $LOGFILE $LOGFILE.0
        cp /dev/null $LOGFILE
    fi
}


#
# Fomart memory info
#
fomart_log_memory_info()
{
    local pid=$1
    local proc=$2

    if [ x"$pid" == "x" ]; then
        red_echo "the proc:$proc may be leaved!!!"
        return
    fi

    local status=$(cat /proc/$pid/status)
    local vmpeak=$(echo "$status" | grep "VmPeak" | grep -v grep | awk '{print $2}')
    local vmsize=$(echo "$status" | grep "VmSize" | grep -v grep | awk '{print $2}')
    local vmhwm=$(echo "$status" | grep "VmHWM" | grep -v grep | awk '{print $2}')
    local vmrss=$(echo "$status" | grep "VmRSS" | grep -v grep | awk '{print $2}')
    local threads=$(echo "$status" | grep "Threads" | grep -v grep | awk '{print $2}')
    local info="[$proc] [$pid] [VmPeak:$vmpeak] [VmSize:$vmsize] [VmHWM:$vmhwm] [VmRSS:$vmrss] [Threads:$threads]"
    red_echo "$info"
}


#
# Log process' memory info
#
monitor_log()
{
    local ps_info="$(ps)"
    local monitor_map="$1"
    local index=0

    limit_log_size
    red_echo "---------------------NO.$MONITOR_LOG_COUNT---------------------"
    red_echo ""

    for proc in ${monitor_map}; do
        if [ $((index%2)) -eq 0 ]; then
            if [ "$proc" = "miio_client" ]; then proc="miio_client -l";fi
            local pid="$(echo "$ps_info" | grep "$proc" | grep -v grep | grep -v logger | awk '{print $1}')"
            fomart_log_memory_info "$pid" "$proc"
        fi

        let index++
    done

    red_echo ""

    let MONITOR_LOG_COUNT++
}


#
# Check process and try to recover if it leaved.
#
watching_and_recover()
{
    local proc_list="$1"
    local monitor_map="$2"
    local index=0
    local online=1

    for proc in ${monitor_map}; do
        if test $((index%2)) -eq 0; then
            green_echo "check $proc"
            match_substring "$proc_list" "$proc"
            [ $? -ne 1 ] && [ "$(agetprop sys.${proc}_stop)" != "true" ] && online=0 || online=1
        elif [ $online -eq 0 ]; then
            #
            #    Sometimes, it takes a period for other worker, such
            #  as to do network-rest.
            #
            local delay=`$GETPROP sys.app_monitor_delay`
            if [ "$delay" != "" ]; then $SETPROP sys.app_monitor_delay; sleep "$delay"; return; fi

            #
            #    If the process was leaved, calling handler, and then
            #  check the return value to decide whether to continue.
            #
            eval $proc; if [ $? -eq 1 ]; then return; fi

            online=1
        fi

        let index++
    done
}

#
# Daemon function.
#
func_daemon()
{
    local suffix=" "

    local content=`ps`
    if [ "$content" = "" ]; then return; fi

    if [ "$CLOUD" = "aiot" ]; then watching_and_recover "${content}${suffix}" "$aiot_map"; return; fi

    if [ "$CLOUD" = "miot" ]; then watching_and_recover "${content}${suffix}" "$miot_map"; return; fi
}

#
# Ticker, see the variable period to know tick.
#
on_ticker()
{
    let ticker_count++

    if [ $(( $ticker_count % $PERIOD)) -eq 0 ]; then
        func_daemon
    fi

    # 5 mins.
    if [ $(( $ticker_count % 300 )) -eq 0 ]; then
        local memfree=`cat /proc/meminfo | grep MemFree | tr -cd "[0-9]"`
        green_echo "Memory free: $memfree"

        # Less than 15MB(15,360KB), do drop.
        if [ $memfree -lt 15360 ]; then echo 3 >/proc/sys/vm/drop_caches; fi
    fi

    if [ $((ticker_count % $MONITOR_LOG_PERIOD)) -eq 0 ]; then
        local monitor_map=
        [ "$CLOUD" = "miot" ] && monitor_map="$miot_map"
        [ "$CLOUD" = "aiot" ] && monitor_map="$aiot_map"
        [ "x$monitor_map" != "x" ] && monitor_log "$monitor_map"
    fi

    if [ $ticker_count -ge $((2**63-2)) ]; then
        ticker_count=0
    fi
}

#
# Main function.
#
main()
{
    initial
    while [ 1 ]; do sleep 1; on_ticker; done
}

#
# Run monitor.
#
green_echo "app_monitor.sh REVISION: $REVISION"; main $@
