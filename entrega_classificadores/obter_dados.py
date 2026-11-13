"""Aquisição oficial com cache local e integridade do snapshot disponibilizado."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import urllib.request,json,re,hashlib

def obter_dados(root):
    root=Path(root);raw=root/'dados/brutos';raw.mkdir(parents=True,exist_ok=True)
    if (raw/'manifesto_aquisicao.json').exists():
        manifest=json.loads((raw/'manifesto_aquisicao.json').read_text())
        for row in manifest:
            p=raw/f'cttu_{row["ano"]}.csv'
            if p.exists() and row.get('sha256') and hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError(f'Hash divergente: {p.name}. Preserve e revise a versão antes de analisar.')
    needed=[raw/f'cttu_{y}.csv' for y in range(2015,2025)]+[raw/'bairros_oficiais.csv',raw/'bairros_oficiais.geojson']
    if all(p.exists() and p.stat().st_size>100 for p in needed):
        print('Snapshot local completo: dez anos, cadastro e malha oficial.');return
    portal='https://dados.recife.pe.gov.br'
    def catalogo(dataset):
        j=json.load(urllib.request.urlopen(portal+'/api/3/action/package_show?id='+dataset,timeout=45))
        if not j.get('success'):raise RuntimeError('CKAN sem sucesso')
        return j
    j=catalogo('acidentes-de-transito-com-e-sem-vitimas');(raw/'catalogo_cttu.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
    resources=[]
    for rec in j['result']['resources']:
        m=re.search(r'20(?:1[5-9]|2[0-4])',rec.get('name',''))
        if m and rec.get('format','').lower()=='csv':resources.append((int(m[0]),rec))
    if len(resources)!=10:raise RuntimeError('Catálogo não retornou exatamente dez anos; revisar os recursos.')
    def download(item):
        year,rec=item;p=raw/f'cttu_{year}.csv'
        if not p.exists():
            req=urllib.request.Request(rec['url'],headers={'Cache-Control':'no-cache','User-Agent':'Projeto5-Academico'})
            b=urllib.request.urlopen(req,timeout=90).read()
            if len(b)<100 or b.lstrip().startswith(b'<'):raise RuntimeError('Download não é CSV: '+str(year))
            p.write_bytes(b)
        b=p.read_bytes();print(year,len(b),'bytes')
        return {'ano':year,'recurso_id':rec['id'],'url':rec['url'],'bytes':len(b),
          'sha256':hashlib.sha256(b).hexdigest(),'obtido_utc':datetime.now(timezone.utc).isoformat(),'resultado':'obtido'}
    with ThreadPoolExecutor(max_workers=5) as ex:manifest=list(ex.map(download,resources))
    (raw/'manifesto_aquisicao.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    j=catalogo('area-urbana');(raw/'catalogo_area_urbana.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
    ids={'a378d50a-5e55-4956-a28c-13305acfc2b3':'bairros_oficiais.csv','5c67ce14-1799-40c4-a37c-9daa04d1761c':'bairros_oficiais.geojson'}
    for rec in j['result']['resources']:
        if rec['id'] in ids:
            p=raw/ids[rec['id']]
            if not p.exists():p.write_bytes(urllib.request.urlopen(rec['url'],timeout=90).read())
    if not all(p.exists() for p in needed):raise RuntimeError('Aquisição incompleta; nenhum resultado será inventado.')

if __name__=='__main__':obter_dados(Path(__file__).resolve().parent)
