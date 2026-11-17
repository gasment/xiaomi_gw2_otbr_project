"""Read-only real gateway diagnostic subscription for the no-attach test."""
import asyncio
from pathlib import Path
import sys
import yaml
from aioesphomeapi import APIClient

root=Path(__file__).resolve().parent.parent
from gateway_test_data import noattach_secrets
secrets=noattach_secrets(sys.argv[1] if len(sys.argv)>1 else None)
host=sys.argv[1] if len(sys.argv)>1 else 'GATEWAY_ADDRESS'
name='mi-gateway2-otbr-test'
expected={'rcp_connectivity','thread_attached','thread_role','rcp_version','radio_version','rloc16','thread_identity','neighbor_count','child_count'}

async def main():
    api=APIClient(host,6053,noise_psk=secrets['api_key'],expected_name=name,provide_time=False)
    try:
        await asyncio.wait_for(api.connect(login=True),15)
        info=await api.device_info()
        assert info.name==name
        entities,services=await api.list_entities_services()
        by_name={entity.object_id:entity for entity in entities}
        assert set(by_name)==expected and not services, 'Unexpected diagnostic entity list'
        values={};complete=asyncio.Event()
        def on_state(state):
            values[state.key]=state
            if all(e.key in values for e in entities):complete.set()
        api.subscribe_states(on_state)
        await asyncio.wait_for(complete.wait(),10)
        def state(key):return values[by_name[key].key]
        for key in expected-{'thread_identity'}:assert not state(key).missing_state, 'Missing real diagnostic: '+key
        assert state('rcp_connectivity').state is True, 'RCP power query did not confirm health'
        assert state('thread_attached').state is False, 'Thread unexpectedly attached'
        assert state('thread_role').state=='disabled', 'Thread unexpectedly enabled'
        for key in ['rcp_version','radio_version']:
            assert state(key).state.startswith('SL-OPENTHREAD/2.5.3.0_GitHub-1fceb225b'), 'Unexpected actual RCP version'
        assert state('thread_identity').missing_state, 'Detached Thread identity must remain missing'
        assert state('neighbor_count').state==0 and state('child_count').state==0
        print('HOST_NOATTACH_API_PASS')
        print('Real RCP connected; Thread disabled/not attached; identity missing; neighbor/child counts zero.')
        print('Version:',state('rcp_version').state)
        print('No API command, Thread dataset import or network configuration was sent.')
    finally:await api.disconnect()

asyncio.run(main())
