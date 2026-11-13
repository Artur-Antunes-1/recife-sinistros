"""CTTU 2015-2024: processamento rastreável; não contém dados simulados."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import csv, io, json, re, hashlib, unicodedata, platform
import numpy as np
import pandas as pd
import requests
from scipy import stats, optimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PORTAL = 'https://dados.recife.pe.gov.br'
DATASET = 'acidentes-de-transito-com-e-sem-vitimas'
IDS = dict(zip(range(2015,2025), [
 '58816e1f-18bc-4335-82bf-80ff080cb0e5','edc820d6-0f01-4fd2-b8a4-5a8c95f7e743',
 'd364e034-7e00-41a7-b557-0b16c21814e7','a7b72334-9229-4e52-a6cb-8006de4942e3',
 'c9fe4a98-0f61-4e81-9c4b-a22f8dc6f1a2','b2594588-2aa8-42c4-b96d-246102ecde3c',
 '31ee35d9-6f8e-4694-9492-efe96e902b07','c2281788-2e8c-472c-8812-67c4f85e9272',
 'dbb9165a-7539-4fdd-943a-acffe12df3e0','87ac4237-f5f9-44d2-bcf1-927aaa0a2d31']))
BAIRROS_ID='a378d50a-5e55-4956-a28c-13305acfc2b3'

def chave(x):
    if pd.isna(x): return pd.NA
    s=unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().upper()
    s=' '.join(s.strip().split())
    return s if s else pd.NA

def coluna(x):
    return re.sub(r'[^a-z0-9]+','_',str(chave(x)).lower()).strip('_')

def ler_csv(path):
    blob=Path(path).read_bytes()
    for enc in ['utf-8-sig','cp1252','latin1']:
        try: text=blob.decode(enc)
        except UnicodeDecodeError: continue
        head=text.splitlines()[0]
        sep=max([';',',','\t','|'],key=head.count)
        # Não ignorar linhas malformadas e não converter silenciosamente NA em zero.
        d=pd.read_csv(io.StringIO(text),sep=sep,dtype='string',keep_default_na=False)
        if len(d.columns)<2: raise ValueError(f'CSV inválido: {path}')
        d.columns=[coluna(c) for c in d.columns]
        if d.columns.duplicated().any(): raise ValueError('Colisões de nomes de colunas')
        d=d.apply(lambda s:s.str.strip()).replace(r'^\s*$|^(?i:NA|N/A|NULL|NAN)$',pd.NA,regex=True)
        return d,enc,sep
    raise ValueError(f'Codificação inválida: {path}')

def adquirir(root, timeout=15):
    root=Path(root); raw=root/'dados/brutos'; raw.mkdir(parents=True,exist_ok=True)
    logs=[]; urls={}
    def baixar(url,dest,rotulo):
        entry={'instante_utc':datetime.now(timezone.utc).isoformat(),'recurso':rotulo,'url':url}
        try:
            r=requests.get(url,timeout=timeout,headers={'User-Agent':'Projeto5-CTTU/1.0'})
            entry['http']=r.status_code; r.raise_for_status()
            b=r.content
            if len(b)<100 or b.lstrip().lower().startswith((b'<',b'{')):
                raise ValueError('Resposta não é CSV utilizável')
            # Validar antes de aceitar o arquivo.
            tmp=dest.with_suffix('.tmp'); tmp.write_bytes(b); ler_csv(tmp); tmp.replace(dest)
            entry.update(resultado='obtido',bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
        except Exception as e:
            entry.update(resultado='falha',erro=str(e)[:300])
        logs.append(entry)
        return entry['resultado']=='obtido'
    try:
        u=f'{PORTAL}/api/3/action/package_show?id={DATASET}'
        r=requests.get(u,timeout=timeout);r.raise_for_status();j=r.json()
        if not j.get('success'): raise ValueError('CKAN sem sucesso')
        (raw/'catalogo_cttu.json').write_text(json.dumps(j,ensure_ascii=False,indent=2))
        for rec in j['result']['resources']:
            m=re.search(r'20(?:1[5-9]|2[0-4])',rec.get('name',''))
            if m and rec.get('format','').lower()=='csv': urls[int(m[0])]=rec['url']
        logs.append({'recurso':'catalogo','url':u,'resultado':'obtido','http':r.status_code})
    except Exception as e:
        logs.append({'recurso':'catalogo','url':u,'resultado':'falha','erro':str(e)[:300]})
    def anual(ano):
        p=raw/f'cttu_{ano}.csv'
        if p.exists():
            ler_csv(p);logs.append({'recurso':str(ano),'resultado':'local','url':urls.get(ano,''),
              'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});return
        u=urls.get(ano,f'{PORTAL}/dataset/{DATASET}/resource/{IDS[ano]}/download/acidentes-de-transito-{ano}.csv')
        if not baixar(u,p,str(ano)):
            # Exportação oficial alternativa. O _id desta exportação é técnico, não protocolo.
            baixar(f'{PORTAL}/datastore/dump/{IDS[ano]}?format=csv',p,f'{ano}:datastore')
    with ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(anual,IDS))
    bp=raw/'bairros_oficiais.csv'
    if not bp.exists(): baixar(f'{PORTAL}/datastore/dump/{BAIRROS_ID}?format=csv',bp,'bairros')
    pd.DataFrame(logs).to_csv(root/'log_aquisicao.csv',index=False)
    return pd.DataFrame(logs)

def preparar(root):
    root=Path(root); bases=[]; inventario=[]; dup=[]
    for ano in IDS:
        path=root/f'dados/brutos/cttu_{ano}.csv'
        if not path.exists(): continue
        d,enc,sep=ler_csv(path); orig=d.columns.tolist(); n=len(d)
        d['ano_origem']=ano; d['arquivo_origem']=path.name
        # Número ordinal do registro de dados; não é linha física se houver CSV multilinha.
        d['registro_origem']=np.arange(1,n+1)
        d['id_rastreio']=str(ano)+':'+d.registro_origem.astype(str)
        d['duplicado_exato']=d.duplicated(subset=[c for c in orig if c!='id'],keep=False)
        if 'protocolo' in d:
            d['protocolo_repetido']=d.protocolo.notna() & d.protocolo.duplicated(keep=False)
        else: d['protocolo_repetido']=False
        # Mesmo protocolo com conteúdo exatamente igual: cópia técnica demonstrável.
        rem=d.duplicated(subset=[c for c in orig if c!='id'],keep='first')
        rem &= d.get('protocolo',pd.Series(pd.NA,index=d.index)).notna()
        d['excluir_copia_tecnica']=rem
        dup.append(d.loc[d.duplicado_exato|d.protocolo_repetido].copy())
        for c in ['data','hora','bairro','situacao','tipo','natureza','natureza_acidente','vitimas','vitimasfatais']:
            if c not in d:d[c]=pd.NA
        # ISO deve preceder a interpretação brasileira: evita trocar mês e dia em ISO.
        s=d.data.astype('string');iso=s.str.match(r'^\d{4}-\d{2}-\d{2}',na=False)
        dt=pd.Series(pd.NaT,index=d.index,dtype='datetime64[ns]')
        dt.loc[iso]=pd.to_datetime(s[iso],format='ISO8601',errors='coerce')
        dt.loc[~iso]=pd.to_datetime(s[~iso],format='mixed',dayfirst=True,errors='coerce')
        d['data_dt']=dt.dt.normalize()
        d['data_valida']=dt.notna() & dt.dt.year.eq(ano)
        d['ano_divergente']=dt.notna() & ~dt.dt.year.eq(ano)
        h=d.hora.astype('string').str.extract(r'^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$')
        hh=pd.to_numeric(h[0],errors='coerce'); mm=pd.to_numeric(h[1],errors='coerce'); ss=pd.to_numeric(h[2],errors='coerce').fillna(0)
        d['hora_n']=hh.where(hh.between(0,23)&mm.between(0,59)&ss.between(0,59))
        for c in ['bairro','situacao','tipo','natureza','natureza_acidente']:d[c+'_chave']=d[c].map(chave)
        for c in ['vitimas','vitimasfatais']:
            x=pd.to_numeric(d[c].astype('string').str.replace(',','.',regex=False),errors='coerce')
            d[c+'_n']=x.where(x.ge(0)&x.mod(1).eq(0))
        inventario.append({'ano':ano,'linhas_brutas':n,'copias_tecnicas':int(rem.sum()),
            'encoding':enc,'separador':sep,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'colunas_originais':json.dumps(orig,ensure_ascii=False)})
        bases.append(d)
    if not bases: return None,{},pd.DataFrame()
    bruto=pd.concat(bases,ignore_index=True,sort=False)
    base=bruto.loc[~bruto.excluir_copia_tecnica].copy()
    t={'inventario':pd.DataFrame(inventario),'duplicidades_auditoria':pd.concat(dup,ignore_index=True)}
    t['qualidade_datas_horas']=base.groupby('ano_origem').agg(linhas=('id_rastreio','size'),
        datas_validas=('data_valida','sum'),ano_divergente=('ano_divergente','sum'),horas_validas=('hora_n','count'))
    t['status']=base.groupby(['ano_origem','situacao_chave'],dropna=False).size().rename('chamados').reset_index()
    aus=[]
    for a,g in bruto.groupby('ano_origem'):
        cols=json.loads(t['inventario'].set_index('ano').loc[a,'colunas_originais'])
        for c in ['data','hora','bairro','situacao','tipo','natureza','natureza_acidente','vitimas','vitimasfatais']:
            aus.append({'ano':a,'campo':c,'existe_na_origem':c in cols,'total':len(g),
              'ausentes':int(g[c].isna().sum()),'pct_ausente':100*g[c].isna().mean()})
    t['ausencias']=pd.DataFrame(aus)
    # Validação estrita contra a relação oficial, sem fuzzy matching nem equivalências inventadas.
    bp=root/'dados/brutos/bairros_oficiais.csv'; nomes=[]
    if bp.exists():
        b,_,_=ler_csv(bp)
        if 'bairro' not in b: raise ValueError('Relação oficial não contém campo bairro')
        nomes=b.bairro.map(chave).dropna().unique().tolist()
        if b.bairro.map(chave).dropna().duplicated().any():raise ValueError('Colisão na relação de bairros')
    base['bairro_validado']=base.bairro_chave.isin(nomes) if nomes else False
    t['bairros_nao_validados']=base.loc[~base.bairro_validado].groupby(['ano_origem','bairro_chave'],dropna=False).size().rename('chamados').reset_index()
    return base,t,bruto

def resumo(s):
    s=pd.to_numeric(pd.Series(s),errors='coerce').dropna().astype(float); n=len(s)
    if not n:return {'n':0}
    vc=s.value_counts();rep=vc.max();modas=sorted(vc[vc.eq(rep)].index.tolist()) if rep>1 else []
    q1,q3=s.quantile([.25,.75]); v=s.var(ddof=1); dp=s.std(ddof=1)
    return {'n':n,'media':s.mean(),'mediana':s.median(),
     'modas':json.dumps(modas),'frequencia_moda':int(rep),'minimo':s.min(),'maximo':s.max(),
     'amplitude':s.max()-s.min(),'variancia_amostral':v,'desvio_padrao_amostral':dp,
     'q1':q1,'q3':q3,'iqr':q3-q1,'p05':s.quantile(.05),'p90':s.quantile(.90),'p95':s.quantile(.95),'p99':s.quantile(.99),
     'cv_pct':100*dp/s.mean() if s.mean()>0 else np.nan,
     'assimetria_fisher':s.skew() if n>=3 and s.nunique()>1 else np.nan,
     'curtose_excesso_fisher':s.kurt() if n>=4 and s.nunique()>1 else np.nan,
     'variancia_media':v/s.mean() if s.mean()>0 else np.nan,'pct_zeros':100*s.eq(0).mean(),
     'extremos_tukey':int(((s<q1-1.5*(q3-q1))|(s>q3+1.5*(q3-q1))).sum())}

def modelos(s):
    x=np.asarray(s,dtype=float);mu=x.mean();n=len(x)
    if n<30 or mu<=0:return {'n':n,'diagnostico':'insuficiente'}
    lp=stats.poisson.logpmf(x,mu).sum();var=x.var()
    init=max(mu*mu/max(var-mu,.01),.01)
    fit=optimize.minimize_scalar(lambda logr:-stats.nbinom.logpmf(x,np.exp(logr),np.exp(logr)/(np.exp(logr)+mu)).sum(),
        bounds=(-10,18),method='bounded')
    r=np.exp(fit.x);p=r/(r+mu)
    return {'n':n,'media':mu,'variancia_media':x.var(ddof=1)/mu,'poisson_aic':2-2*lp,
        'nb_aic':4+2*fit.fun if fit.success else np.nan,'nb_r':r,'nb_p':p,
        'nb_convergiu':bool(fit.success),'nb_fronteira':abs(fit.x-18)<.1 or abs(fit.x+10)<.1,
        'lag1':pd.Series(x).autocorr(1),'diagnostico':'AIC exploratório; dependência e heterogeneidade não controladas'}

def analisar(base,t):
    t=t.copy();valid=base.loc[base.data_valida].copy(); dias=[]
    for a,g in valid.groupby('ano_origem'):
        c=g.groupby('data_dt').size(); idx=pd.date_range(c.index.min(),c.index.max(),freq='D')
        dias.append(pd.DataFrame({'ano':a,'data':idx,'chamados':c.reindex(idx,fill_value=0).values}))
    if not dias:raise ValueError('Nenhuma data válida; análise temporal interrompida')
    diaria=pd.concat(dias,ignore_index=True);diaria['ano_mes']=diaria.data.dt.to_period('M').astype(str)
    mensal=diaria.groupby(['ano','ano_mes']).agg(chamados=('chamados','sum'),dias_janela=('data','size')).reset_index()
    mensal['media_diaria']=mensal.chamados/mensal.dias_janela
    t['diaria']=diaria;t['mensal']=mensal
    anual=base.groupby('ano_origem').size().rename('chamados').to_frame()
    anual['finalizada']=base.loc[base.situacao_chave.eq('FINALIZADA')].groupby('ano_origem').size().reindex(anual.index,fill_value=0)
    anual['pct_excluido_finalizada']=100*(1-anual.finalizada/anual.chamados)
    anual['datas_validas']=valid.groupby('ano_origem').size().reindex(anual.index,fill_value=0)
    anual['primeira_data']=valid.groupby('ano_origem').data_dt.min();anual['ultima_data']=valid.groupby('ano_origem').data_dt.max()
    anual['dias_janela']=(anual.ultima_data-anual.primeira_data).dt.days+1
    anual['media_por_dia_janela']=anual.datas_validas/anual.dias_janela
    anual['dias_sem_registro']=diaria.groupby('ano').chamados.apply(lambda x:x.eq(0).sum())
    anual['variacao_pct']=anual.chamados.pct_change(fill_method=None)*100
    anual['ressalva']='Janela observada não comprova cobertura; 2015 parcial'
    t['anual']=anual
    for name,table in [('diaria',diaria),('mensal',mensal)]:
        t['estatisticas_'+name+'_ano']=pd.DataFrame([{'ano':a,**resumo(g.chamados)} for a,g in table.groupby('ano')])
    t['estatisticas_globais']=pd.DataFrame([{'unidade':'chamados/dia',**resumo(diaria.chamados)},
        {'unidade':'chamados/mês',**resumo(mensal.chamados)},
        {'unidade':'totais anuais 2016-2024 presentes',**resumo(anual.loc[anual.index!=2015,'chamados'])}])
    t['modelos_diarios']=pd.DataFrame([{'ano':a,**modelos(g.chamados)} for a,g in diaria.groupby('ano')])
    # Extremos são sinalizados, nunca removidos como erro por critério estatístico.
    outs=[]
    for a,g in mensal.groupby('ano'):
        q1,q3=g.chamados.quantile([.25,.75]);z=g[(g.chamados<q1-1.5*(q3-q1))|(g.chamados>q3+1.5*(q3-q1))]
        outs.append(z)
    t['meses_extremos_tukey']=pd.concat(outs)
    dow=valid.data_dt.dt.dayofweek.value_counts().reindex(range(7),fill_value=0)
    expos=diaria.data.dt.dayofweek.value_counts().reindex(range(7),fill_value=0)
    t['dia_semana']=pd.DataFrame({'chamados':dow,'dias_janela':expos,'chamados_por_dia_janela':dow/expos})
    h=base.hora_n.dropna().astype(int).value_counts().reindex(range(24),fill_value=0)
    t['hora']=pd.DataFrame({'chamados':h,'pct_horarios_validos':100*h/max(h.sum(),1)})
    t['calendario_mes']=mensal.assign(mes=mensal.ano_mes.str[-2:].astype(int)).groupby('mes').agg(
        chamados=('chamados','sum'),meses_observados=('chamados','size'),media_por_mes=('chamados','mean'))
    t['estatisticas_diaria_semana']=pd.DataFrame([{'dia_semana':a,**resumo(g.chamados)}
        for a,g in diaria.groupby(diaria.data.dt.dayofweek)])
    t['horas_ano']=base.groupby(['ano_origem','hora_n'],dropna=False).size().rename('chamados').reset_index()
    # Não agregar categorias de anos diferentes: preservar ano + campo + rótulo.
    cats=[]; sensitivity=[]
    for campo in ['tipo','natureza','natureza_acidente','bairro']:
        key=campo+'_chave'
        z=base.groupby(['ano_origem',key],dropna=False).size().rename('chamados').reset_index().rename(columns={key:'categoria'})
        z['campo']=campo;z['pct_ano']=100*z.chamados/z.ano_origem.map(anual.chamados)
        cats.append(z)
        f=base.loc[base.situacao_chave.eq('FINALIZADA')].groupby(['ano_origem',key],dropna=False).size().rename('finalizada').reset_index().rename(columns={key:'categoria'})
        z=z.merge(f,on=['ano_origem','categoria'],how='left');z['finalizada']=z.finalizada.fillna(0).astype(int)
        z['pct_retido_finalizada']=100*z.finalizada/z.chamados;sensitivity.append(z)
    t['categorias_por_ano']=pd.concat(cats,ignore_index=True)
    t['sensibilidade_status_categorias']=pd.concat(sensitivity,ignore_index=True)
    b=base.loc[base.bairro_validado].groupby('bairro_chave').size().rename('chamados').sort_values(ascending=False).to_frame()
    if len(b):
        oficiais,_,_=ler_csv(Path(base.attrs['root'])/'dados/brutos/bairros_oficiais.csv')
        b=b.reindex(oficiais.bairro.map(chave).dropna().unique(),fill_value=0).sort_values('chamados',ascending=False)
        b['pct_bairros_validos']=100*b.chamados/b.chamados.sum();b['pct_acumulado']=b.pct_bairros_validos.cumsum()
        t['bairros']=b;t['estatisticas_bairros']=pd.DataFrame([resumo(b.chamados)])
        t['bairro_ano']=base.loc[base.bairro_validado].groupby(['ano_origem','bairro_chave']).size().unstack(fill_value=0).reindex(columns=b.index,fill_value=0)
        t['estatisticas_bairro_ano']=pd.DataFrame([{'ano':a,**resumo(g)} for a,g in t['bairro_ano'].iterrows()])
    grav=[]
    for a,g in base.groupby('ano_origem'):
        for campo in ['vitimas','vitimasfatais']:
            x=g[campo+'_n'];n=x.count()
            grav.append({'ano':a,'campo':campo,'total_registros':len(g),'validos':n,
             'ausentes':int(g[campo].isna().sum()),'presentes_invalidos':int((g[campo].notna()&x.isna()).sum()),
             'cobertura_pct':100*n/len(g),'zeros_explicitos':int(x.eq(0).sum()),'valores_positivos':int(x.gt(0).sum()),
             'soma_campo_observado':x.sum(min_count=1),'comparabilidade_historica':'NÃO VALIDADA',**resumo(x)})
    t['gravidade_campo_observado']=pd.DataFrame(grav)
    return t

def exportar(base,t,root):
    root=Path(root);out=root/'tabelas';out.mkdir(exist_ok=True)
    for name,d in t.items():d.to_csv(out/f'{name}.csv',index=True,encoding='utf-8-sig')
    p=root/'dados/tratados';p.mkdir(parents=True,exist_ok=True)
    base.to_csv(p/'chamados_tratados.csv.gz',index=False,compression='gzip')
    (root/'ambiente.json').write_text(json.dumps({'python':platform.python_version(),'pandas':pd.__version__,
      'numpy':np.__version__,'matplotlib':matplotlib.__version__},indent=2))

def graficos(t,root):
    root=Path(root);out=root/'graficos';out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':220})
    def save(fig,name,title,x,y):
        ax=fig.axes[0];ax.set(title=title,xlabel=x,ylabel=y)
        fig.text(.01,.01,'Fonte: Prefeitura do Recife / CTTU. Chamados; 2015 parcial. Sem filtro de status.',fontsize=8)
        fig.tight_layout(rect=(0,.05,1,1));fig.savefig(out/f'{name}.png');plt.close(fig)
    a=t['anual'];m=t['mensal'];d=t['diaria'];color='#147D92'
    fig,ax=plt.subplots(figsize=(10,4));ax.plot(a.index,a.chamados,'o-',label='Todos');ax.plot(a.index,a.finalizada,'o--',label='FINALIZADA');ax.legend();ax.set_xticks(a.index)
    save(fig,'01_anual','Chamados por ano de origem | 2015-2024','Ano','Chamados no arquivo')
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(pd.to_datetime(m.ano_mes),m.chamados,color=color)
    save(fig,'02_mensal','Série mensal | janelas observadas de 2015-2024','Ano/mês','Chamados/mês')
    for name,s,unit in [('03_hist_mensal',m.chamados,'mês'),('04_hist_diario',d.chamados,'dia')]:
        fig,ax=plt.subplots(figsize=(9,4));ax.hist(s,bins='fd',color=color,edgecolor='white');ax.axvline(s.mean(),label='Média',color='#C36D22');ax.axvline(s.median(),label='Mediana',color='#7D3D91',ls='--');ax.legend()
        save(fig,name,f'Distribuição de contagens por {unit} | 2015-2024',f'Chamados/{unit}',f'Frequência de {unit}s')
    fig,ax=plt.subplots(figsize=(10,4));years=sorted(m.ano.unique());ax.boxplot([m.loc[m.ano.eq(a),'chamados'] for a in years],tick_labels=years,showmeans=True)
    save(fig,'05_boxplot','Dispersão mensal e extremos de Tukey | 2015-2024','Ano','Chamados/mês')
    fig,ax=plt.subplots(figsize=(9,4));z=t['dia_semana'];ax.bar(['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'],z.chamados_por_dia_janela,color=color)
    save(fig,'06_semana','Chamados por dia da semana | janelas de 2015-2024','Dia da semana','Chamados por dia da janela')
    fig,ax=plt.subplots(figsize=(10,4));ax.bar(t['hora'].index,t['hora'].chamados,color=color);ax.set_xticks(range(0,24,2))
    save(fig,'07_hora','Horários válidos dos chamados | 2015-2024','Hora local registrada','Chamados')
    fig,ax=plt.subplots(figsize=(10,4));z=t['ausencias'].pivot(index='ano',columns='campo',values='pct_ausente');im=ax.imshow(z,aspect='auto',vmin=0,vmax=100,cmap='YlOrRd');ax.set_xticks(range(len(z.columns)),z.columns,rotation=35,ha='right');ax.set_yticks(range(len(z)),z.index);fig.colorbar(im,ax=ax,label='% ausente (inclui coluna inexistente)')
    save(fig,'08_ausencias','Ausências nos arquivos brutos | 2015-2024','Campo','Ano')
    if 'bairros' in t:
        b=t['bairros'];fig,ax=plt.subplots(figsize=(10,6));z=b.head(15).iloc[::-1];ax.barh(z.index,z.chamados,color=color)
        save(fig,'09_bairros','15 bairros oficiais com mais chamados | 2015-2024','Chamados','Bairro')
        fig,ax=plt.subplots(figsize=(9,4));ax.hist(b.chamados,bins='fd',color=color);ax.axvline(b.chamados.mean(),color='#C36D22',label='Média');ax.axvline(b.chamados.median(),ls='--',color='#7D3D91',label='Mediana');ax.legend()
        save(fig,'10_hist_bairros','Concentração entre bairros oficiais | 2015-2024','Chamados/bairro','Bairros')
    z=t['categorias_por_ano'];z=z.loc[z.campo.eq('tipo')&z.categoria.notna()]
    if len(z):
        fig,axs=plt.subplots(5,2,figsize=(13,17))
        for ax,year in zip(axs.flat,IDS):
            sub=z[z.ano_origem.eq(year)].nlargest(5,'chamados').iloc[::-1];ax.barh(sub.categoria,sub.pct_ano,color=color);ax.set_title(str(year));ax.set_xlabel('% de todos os chamados do ano');ax.tick_params(labelsize=8)
        fig.suptitle('Tipos por ano | rótulos sem equivalência histórica presumida')
        fig.text(.01,.01,'Fonte: Prefeitura do Recife / CTTU. Top 5 em cada ano; categorias omitidas não somam 100%.',fontsize=9)
        fig.tight_layout(rect=(0,.03,1,.98));fig.savefig(out/'11_tipos_por_ano.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4))
    for year,g in m.groupby('ano'):ax.plot(pd.to_datetime(g.ano_mes).dt.month,g.media_diaria,marker='.',label=str(year))
    ax.legend(ncol=5,fontsize=8);ax.set_xticks(range(1,13))
    save(fig,'12_comparacao_meses','Perfil mensal por ano | intensidade na janela observada','Mês','Chamados/dia da janela')
    # QQ normal e PMFs por ano evitam atribuir distribuição única a dez regimes.
    fig,axs=plt.subplots(5,2,figsize=(11,15))
    for ax,(year,g) in zip(axs.flat,d.groupby('ano')):
        stats.probplot(g.chamados,dist='norm',plot=ax);ax.set_title(str(year));ax.set_xlabel('Quantil normal teórico');ax.set_ylabel('Chamados/dia')
    fig.suptitle('QQ normal | contagens diárias; diagnóstico visual, sem declaração de normalidade')
    fig.text(.01,.01,'Fonte: Prefeitura do Recife / CTTU. Discrição, dependência temporal e mudanças de cobertura limitam a hipótese normal.',fontsize=8)
    fig.tight_layout(rect=(0,.03,1,.98));fig.savefig(out/'13_qq_normal.png');plt.close(fig)

def executar(root='.',download=True):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if download:adquirir(root)
    base,t,bruto=preparar(root)
    anos=sorted(base.ano_origem.unique().tolist()) if base is not None else []
    status={'instante_utc':datetime.now(timezone.utc).isoformat(),'anos_processados':anos,
       'registros_brutos':len(bruto),'registros_analiticos':len(base) if base is not None else 0,
       'todos_anos':anos==list(IDS),'analise_empirica_executada':base is not None,
       'aviso':'Janela observada não comprova cobertura. Comparabilidade semântica de fatalidades NÃO validada.'}
    if base is None:
        status['bloqueio']='Nenhum CSV disponível. Nenhuma tabela estatística ou figura empírica foi produzida.'
    else:
        base.attrs['root']=str(root);t=analisar(base,t);exportar(base,t,root);graficos(t,root)
    (root/'status_execucao.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
    return status,t

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--sem-download',action='store_true');a=p.parse_args()
    print(json.dumps(executar(a.root,not a.sem_download)[0],ensure_ascii=False,indent=2))
