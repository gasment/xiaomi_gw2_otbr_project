# Preserve the locked checkout: patch a build-local copy, with strict anchors.
set(discovery_original "${OTBR_HOST_ROOT}/vendor/ot-br-posix/third_party/openthread/repo/src/core/thread/mle_ftd.cpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${discovery_original}")
file(READ "${discovery_original}" discovery_contents)
set(discovery_anchor "            mDiscoveryRequestCallback.Invoke(&info);")
string(FIND "${discovery_contents}" "${discovery_anchor}" discovery_found)
string(REGEX MATCHALL "mDiscoveryRequestCallback[.]Invoke" discovery_matches "${discovery_contents}")
list(LENGTH discovery_matches discovery_count)
if(discovery_found EQUAL -1 OR NOT discovery_count EQUAL 1)
  message(FATAL_ERROR "Unsupported OpenThread discovery callback layout")
endif()
set(discovery_replacement [=[            OffsetRange joinerAdvertisementRange;
            bool identified = false;
            if (info.mIsJoiner &&
                Tlv::FindTlvValueOffsetRange(aRxInfo.mMessage, Tlv::kDiscovery, joinerAdvertisementRange) == kErrorNone)
            {
                identified = thread_br_joiner_discovery_report(&info.mExtAddress, info.mVersion, &aRxInfo.mMessage,
                    joinerAdvertisementRange.GetOffset(), joinerAdvertisementRange.GetLength());
            }
            if (!identified)
            {
                mDiscoveryRequestCallback.Invoke(&info);
            }]=])
string(REPLACE "${discovery_anchor}" "${discovery_replacement}" discovery_contents "${discovery_contents}")
string(FIND "${discovery_contents}" "#include \"mle.hpp\"" discovery_include)
if(discovery_include EQUAL -1)
  message(FATAL_ERROR "Unsupported OpenThread MLE include layout")
endif()
string(REPLACE "#include \"mle.hpp\"" "#include \"thread/mle.hpp\"" discovery_contents "${discovery_contents}")
set(discovery_patched "${CMAKE_CURRENT_BINARY_DIR}/mle_ftd_commissioner.cpp")
file(WRITE "${discovery_patched}" "#include \"otbr_host/commissioner_discovery.h\"\n${discovery_contents}")
get_target_property(discovery_sources openthread-ftd SOURCES)
set(discovery_source_found FALSE)
foreach(source IN LISTS discovery_sources)
  if(source MATCHES "(^|/)mle_ftd\\.cpp$")
    list(REMOVE_ITEM discovery_sources "${source}")
    set(discovery_source_found TRUE)
  endif()
endforeach()
if(NOT discovery_source_found)
  message(FATAL_ERROR "OpenThread mle_ftd.cpp not found in FTD source list")
endif()
set_property(TARGET openthread-ftd PROPERTY SOURCES "${discovery_sources}")
target_compile_definitions(ot-config INTERFACE OPENTHREAD_CONFIG_MLE_DISCOVERY_SCAN_REQUEST_CALLBACK_ENABLE=1)
target_include_directories(openthread-ftd PRIVATE "${OTBR_HOST_ROOT}/include")
target_sources(openthread-ftd PRIVATE "${discovery_patched}" "${OTBR_HOST_ROOT}/src/commissioner_discovery.cpp")
