import concurrent.futures, hashlib, json
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import pymupdf

ROOT = Path(__file__).parent
SOURCES = {
 'llm-falsifier':'https://arxiv.org/html/2609.20752v1',
 'tracebench':'https://arxiv.org/html/2608.27182v1',
 'llmad':'https://arxiv.org/pdf/2405.15370',
 'guarded-falsification':'https://research.abo.fi/files/80166889/3832139.pdf',
 'llm-tsad':'https://proceedings.neurips.cc/paper_files/paper/2025/file/950a34c7b107111570077078e1b5b8ef-Paper-Conference.pdf',
 'anomllm':'https://proceedings.iclr.cc/paper_files/paper/2025/file/05774fb74e863308c4b460c9f49f6918-Paper-Conference.pdf',
 'integration-negative':'https://arxiv.org/html/2610.05031v1',
 'appliance-diagnosis':'https://arxiv.org/html/2610.19291v1',
 'batteryagent':'https://arxiv.org/html/2512.24686v1',
 'fd-llm':'https://arxiv.org/html/2412.01218v1',
}

def fetch(item):
    key,url=item
    row={'id':key,'url':url}
    try:
        r=requests.get(url,timeout=(15,55))
        row.update(status=r.status_code, final_url=r.url)
        r.raise_for_status()
        ispdf=r.content.startswith(b'%PDF')
        suffix='.pdf' if ispdf else '.html'
        (ROOT/(key+suffix)).write_bytes(r.content)
        if ispdf:
            doc=pymupdf.open(stream=r.content,filetype='pdf')
            txt='\n'.join(f'\nPAGE {i+1}\n'+p.get_text() for i,p in enumerate(doc))
            row['pages']=len(doc)
        else:
            soup=BeautifulSoup(r.content,'html.parser')
            for tag in soup(['script','style']): tag.decompose()
            txt=soup.get_text('\n',strip=True)
        (ROOT/(key+'.txt')).write_text(txt,encoding='utf-8')
        row.update(sha256=hashlib.sha256(r.content).hexdigest(),characters=len(txt))
    except Exception as e: row['error']=str(e)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(fetch,SOURCES.items()))
    (ROOT/'source-manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
