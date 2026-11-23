"""Freeze the official SCU35 board files at Vivado's recorded catalog commit."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET


def main():
    root=Path(__file__).resolve().parents[1]
    commit='29bbdfd89b7048cac72bf971bcd4b18f6ca50c5a'
    catalog=Path.home()/'AppData/Roaming/Xilinx/Vivado/2025.2/xhub/board_store/xilinx_board_store/XilinxBoardStore/Vivado/2025.2/catalog/vivado_2025.2.json'
    text=catalog.read_text();assert commit in text and 'boards/Xilinx/scu35/1.0' in text
    api='https://api.github.com/repos/Xilinx/XilinxBoardStore/contents/boards/Xilinx/scu35/1.0?ref='+commit
    def get(url):
        request=urllib.request.Request(url,headers={'User-Agent':'Parser-FPGA-board-audit'})
        with urllib.request.urlopen(request,timeout=30)as response:return response.read()
    listing=json.loads(get(api))
    assert {e['name']for e in listing}=={'LICENSE','board.xml','changelog.txt','part0_pins.xml','preset.xml','xitem.json'}
    target=root/'FPGA/boards/scu35/1.0';target.mkdir(parents=True,exist_ok=False)
    evidence=root/'build/validation/scu35-board-definition';evidence.mkdir(parents=True,exist_ok=False)
    artifacts={}
    for e in listing:
        assert e['type']=='file' and e['download_url'].startswith('https://raw.githubusercontent.com/Xilinx/XilinxBoardStore/'+commit+'/boards/Xilinx/scu35/1.0/')
        content=get(e['download_url']);assert len(content)==e['size']
        assert hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()==e['sha']
        (target/e['name']).write_bytes(content)
        artifacts[e['name']]=dict(sha256=hashlib.sha256(content).hexdigest(),git_blob_sha1=e['sha'],url=e['download_url'])
    board=ET.parse(target/'board.xml');assert board.getroot().attrib['name']=='scu35'
    assert 'xcsu35p-sbvb625-2-e' in(target/'board.xml').read_text()
    result=dict(phase='official_board_files_frozen_vivado_validation_pending',verified_utc=datetime.now(timezone.utc).isoformat(),
        board_part='xilinx.com:scu35:part0:1.0',device='xcsu35p-sbvb625-2-e',upstream_commit=commit,
        source_catalog=str(catalog),source_catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),
        api_listing_url=api,files=artifacts,downloaded_files_modified=False,
        original_projects_modified=False,physical_hardware_available=False,
        synthesis_implementation_and_simulation_are_target_validation=True,
        package_phy_timing_verified=False,board_bringup_verified=False,full_system_complete=False)
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    for p in(evidence/'audit.json',root/'build/validation/scu35-board-definition.json'):
        p.write_text(json.dumps(result,indent=2)+'\n')
    (evidence/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k:result[k]for k in('phase','key','board_part','upstream_commit')}))


if __name__=='__main__':main()
