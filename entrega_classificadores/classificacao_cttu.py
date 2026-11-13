"""Avaliação temporal reproduzível de classificadores de volume de chamados CTTU."""
from pathlib import Path
import json, hashlib, platform, importlib.metadata, shutil, warnings
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (confusion_matrix,accuracy_score,precision_score,recall_score,f1_score,
 roc_auc_score,average_precision_score,roc_curve,precision_recall_curve,balanced_accuracy_score,brier_score_loss)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import preparacao_cttu as prep

NUM=['lag1','lag2','lag3','lag6','media3','media6','dp6','tendencia','mes_sin','mes_cos']
NAMES={'dummy':'Majoritária','persistencia':'Persistência','logistica':'Regressão logística','arvore':'Árvore de decisão'}
COLORS={'dummy':'#9BA8B4','persistencia':'#B68445','logistica':'#127F80','arvore':'#476FB3'}

def dump(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')

def metrics(y,s,threshold):
    pred=np.asarray(s)>=threshold;tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return dict(acuracia=accuracy_score(y,pred),precisao=precision_score(y,pred,zero_division=0),
        recall=recall_score(y,pred,zero_division=0),f1=f1_score(y,pred,zero_division=0),
        acuracia_balanceada=balanced_accuracy_score(y,pred),roc_auc=roc_auc_score(y,s),
        average_precision=average_precision_score(y,s),tn=int(tn),fp=int(fp),fn=int(fn),tp=int(tp),
        n=len(y),positivos=int(np.sum(y)),limiar=float(threshold))

def carregar(root):
    root=Path(root);q=root/'qualidade';q.mkdir(exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',FutureWarning);base,t,bruto=prep.preparar(root)
    if base is None or set(base.ano_origem.unique())!=set(range(2015,2025)):
        raise RuntimeError('São necessários os dez CSVs oficiais de 2015-2024; nenhum dado é simulado.')
    for name,tab in t.items():tab.to_csv(q/f'{name}.csv',index=False,encoding='utf-8-sig')
    oficiais,_,_=prep.ler_csv(root/'dados/brutos/bairros_oficiais.csv')
    bairros=oficiais.bairro.map(prep.chave).tolist()
    # Sem equivalências aproximadas: todo vínculo é exato após normalização textual.
    resumo=[]
    for ano,g in base.groupby('ano_origem'):
        resumo.append({'ano':int(ano),'brutos':int((bruto.ano_origem==ano).sum()),'analiticos':len(g),
          'datas_validas':int(g.data_valida.sum()),'datas_invalidas_ou_outro_ano':int((~g.data_valida).sum()),
          'horas_validas':int(g.hora_n.notna().sum()),'bairro_validado':int(g.bairro_validado.sum()),
          'pct_bairro_validado':100*g.bairro_validado.mean(),
          'finalizada':int(g.situacao_chave.eq('FINALIZADA').sum()),
          'pct_excluido_finalizada':100*(1-g.situacao_chave.eq('FINALIZADA').mean()),
          'vitimasfatais_validos':int(g.vitimasfatais_n.notna().sum()),
          'pct_fatal_ausente':100*g.vitimasfatais_n.isna().mean(),
          'primeira_data_valida':str(g.loc[g.data_valida,'data_dt'].min().date()),
          'ultima_data_valida':str(g.loc[g.data_valida,'data_dt'].max().date())})
    qualidade=pd.DataFrame(resumo);qualidade.to_csv(q/'qualidade_por_ano.csv',index=False,encoding='utf-8-sig')
    # As 36 datas do arquivo de 2024 que pertencem a outro ano são preservadas e excluídas só da dimensão temporal.
    base.to_csv(root/'dados/chamados_tratados.csv.gz',index=False,compression='gzip')
    return base,bairros,qualidade

def painel_mensal(base,bairros):
    v=base.loc[base.data_valida & base.bairro_validado].copy()
    v['periodo']=v.data_dt.dt.to_period('M').astype(str)
    idx=pd.MultiIndex.from_product([bairros,pd.period_range('2021-01','2024-12',freq='M').astype(str)],names=['bairro','periodo'])
    c=v.groupby(['bairro_chave','periodo']).size()
    c.index=c.index.set_names(['bairro','periodo'])
    panel=c.reindex(idx,fill_value=0).rename('chamados').reset_index().sort_values(['bairro','periodo'])
    # Meses sem qualquer chamado municipal sugerem falha de cobertura, não milhares de negativos.
    assert panel.groupby('periodo').chamados.sum().gt(0).all(),'Há mês inteiro sem dados: revisar cobertura antes da modelagem.'
    g=panel.groupby('bairro',sort=False)
    for k in [1,2,3,6]:panel[f'lag{k}']=g.chamados.shift(k)
    for k in [3,6]:panel[f'media{k}']=g.chamados.transform(lambda x:x.shift(1).rolling(k).mean())
    panel['dp6']=g.chamados.transform(lambda x:x.shift(1).rolling(6).std(ddof=0))
    panel['tendencia']=panel.lag1-panel.lag3
    month=panel.periodo.str[-2:].astype(int)
    panel['mes_sin']=np.sin(2*np.pi*month/12);panel['mes_cos']=np.cos(2*np.pi*month/12)
    panel=panel.dropna(subset=NUM).copy()
    panel['particao']=np.select([panel.periodo.le('2022-12'),panel.periodo.le('2023-12')],['treino','validacao'],default='teste')
    treino=panel.loc[panel.particao.eq('treino')]
    corte=max(1,int(np.ceil(treino.chamados.quantile(.75))))
    panel['alvo']=(panel.chamados>=corte).astype(int)
    # Verificação independente: feature mais recente é exatamente o mês anterior do mesmo bairro.
    hist=c.to_dict()
    assert all(row.lag1==hist.get((row.bairro,str(pd.Period(row.periodo)-1)),0) for row in panel.itertuples())
    assert panel.loc[panel.particao.eq('treino'),'periodo'].max()<panel.loc[panel.particao.eq('validacao'),'periodo'].min()
    assert panel.loc[panel.particao.eq('validacao'),'periodo'].max()<panel.loc[panel.particao.eq('teste'),'periodo'].min()
    assert not panel.duplicated(['bairro','periodo']).any()
    return panel,corte

def treinar(panel,corte,out):
    out=Path(out);tab=out/'tabelas';tab.mkdir(parents=True,exist_ok=True)
    train=panel[panel.particao.eq('treino')];val=panel[panel.particao.eq('validacao')];test=panel[panel.particao.eq('teste')]
    pre=ColumnTransformer([('numericas',StandardScaler(),NUM),('bairro',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['bairro'])])
    models={'dummy':Pipeline([('pre',pre),('modelo',DummyClassifier(strategy='prior'))]),
      'logistica':Pipeline([('pre',ColumnTransformer([('numericas',StandardScaler(),NUM),('bairro',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['bairro'])])),('modelo',LogisticRegression(C=1,max_iter=2000,random_state=42))]),
      'arvore':Pipeline([('pre',ColumnTransformer([('numericas','passthrough',NUM),('bairro',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['bairro'])])),('modelo',DecisionTreeClassifier(max_depth=4,min_samples_leaf=30,random_state=42))])}
    scores={};limits={};thresholdrows=[]
    for name in ['dummy','persistencia','logistica','arvore']:
        if name=='persistencia':
            sv=val.lag1.to_numpy()/(val.lag1.to_numpy()+corte);st=test.lag1.to_numpy()/(test.lag1.to_numpy()+corte)
        else:
            models[name].fit(train[NUM+['bairro']],train.alvo)
            sv=models[name].predict_proba(val[NUM+['bairro']])[:,1];st=models[name].predict_proba(test[NUM+['bairro']])[:,1]
        scores[name]={'validacao':sv,'teste':st}
        choices=np.round(np.arange(.05,.951,.01),2) if name in ['logistica','arvore'] else [.5]
        ts=[]
        for threshold in choices:
            z={'modelo':name,'nome':NAMES[name],**metrics(val.alvo,sv,threshold)};thresholdrows.append(z);ts.append(z)
        # Empates: maior recall, depois maior limiar. Toda escolha ocorre em 2023.
        best=sorted(ts,key=lambda z:(z['f1'],z['recall'],z['limiar']),reverse=True)[0];limits[name]=best['limiar']
    rows=[];preds=[]
    for name in scores:
        for part,d in [('validacao',val),('teste',test)]:
            s=scores[name][part];rows.append({'modelo':name,'nome':NAMES[name],'particao':part,**metrics(d.alvo,s,limits[name])})
            z=d[['bairro','periodo','particao','chamados','alvo','lag1','media3','media6']].copy()
            z['modelo']=name;z['score']=s;z['limiar']=limits[name];z['predito']=(s>=limits[name]).astype(int);preds.append(z)
    result=pd.DataFrame(rows)
    # Seleção entre os dois classificadores simples pelo F1 de validação, não pelo teste.
    winner=result[result.particao.eq('validacao')&result.modelo.isin(['logistica','arvore'])].sort_values(['f1','recall','nome'],ascending=[False,False,True]).iloc[0].modelo
    pd.DataFrame(thresholdrows).to_csv(tab/'limiares_validacao.csv',index=False)
    result.to_csv(tab/'metricas.csv',index=False,encoding='utf-8-sig')
    preds=pd.concat(preds,ignore_index=True);preds.to_csv(tab/'predicoes.csv',index=False,encoding='utf-8-sig')
    panel.to_csv(tab/'painel_bairro_mes.csv',index=False,encoding='utf-8-sig')
    split=panel.groupby('particao').agg(n=('alvo','size'),positivos=('alvo','sum'),inicio=('periodo','min'),fim=('periodo','max'))
    split['prevalencia']=split.positivos/split.n;split.to_csv(tab/'particoes.csv')
    for name in models:
        if name=='dummy':continue
        pp=models[name].named_steps['pre'];est=models[name].named_steps['modelo'];names=pp.get_feature_names_out()
        weights=est.coef_[0] if name=='logistica' else est.feature_importances_
        pd.DataFrame({'atributo':names,'peso_ou_importancia':weights}).sort_values('peso_ou_importancia',ascending=False).to_csv(tab/f'atributos_{name}.csv',index=False)
    month=[]
    for (name,period),g in preds[preds.particao.eq('teste')].groupby(['modelo','periodo']):
        month.append({'modelo':name,'periodo':period,**metrics(g.alvo,g.score,limits[name])})
    pd.DataFrame(month).to_csv(tab/'metricas_mensais_teste.csv',index=False)
    # Bootstrap por blocos de mês: mantém dependência entre bairros do mesmo mês.
    rng=np.random.default_rng(42);cis=[];B=1000
    for name in scores:
        z=preds[preds.modelo.eq(name)&preds.particao.eq('teste')].copy();groups=[g for _,g in z.groupby('periodo')]
        vals=[]
        for i in range(B):
            sampled=pd.concat([groups[k] for k in rng.integers(0,len(groups),len(groups))],ignore_index=True)
            y=sampled.alvo.to_numpy();s=sampled.score.to_numpy();p=s>=limits[name]
            if len(np.unique(y))<2:continue
            vals.append([f1_score(y,p,zero_division=0),recall_score(y,p,zero_division=0),precision_score(y,p,zero_division=0),roc_auc_score(y,s),average_precision_score(y,s)])
        arr=np.asarray(vals)
        for j,m in enumerate(['f1','recall','precisao','roc_auc','average_precision']):
            lo,hi=np.quantile(arr[:,j],[.025,.975]);cis.append({'modelo':name,'metrica':m,'ic95_inferior':lo,'ic95_superior':hi,'repeticoes_validas':len(arr),'unidade_bootstrap':'mês; 12 blocos, aproximação exploratória'})
    pd.DataFrame(cis).to_csv(tab/'intervalos_bootstrap_mensal.csv',index=False)
    meta={'classe_positiva':f'Bairro-mês com pelo menos {corte} chamados datados e com bairro validado',
      'corte_contagem':corte,'quantil_treino':.75,'modelo_selecionado':winner,'limiares':limits,
      'hiperparametros':{'logistica':{'C':1,'max_iter':2000},'arvore':{'max_depth':4,'min_samples_leaf':30}},
      'treino':'2021-07 a 2022-12','validacao':'2023-01 a 2023-12','teste':'2024-01 a 2024-12',
      'passo_previsao':'Ao fim de t-1, prever o bairro-mês t; avaliação sequencial de um passo com histórico observado.',
      'treinamento':'Treino somente até dez/2022; não reajustado em 2023 ou 2024.',
      'limiar_selecao':'F1 em validação 2023; desempate por recall, depois maior limiar.',
      'observacao_score':'Scores não calibrados; persistência é índice monotônico, não probabilidade.',
      'bairro_meses':int(len(panel)),'n_bairros':int(panel.bairro.nunique()),'num_features':NUM,
      'seed':42,'data_obtencao':'2026-11-04'}
    dump(out/'metodologia_modelos.json',meta)
    return result,preds,meta,models

def figuras(result,preds,meta,models,out):
    out=Path(out);figdir=out/'graficos';figdir.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':220})
    test=preds[preds.particao.eq('teste')];modelids=['dummy','persistencia','logistica','arvore']
    def save(fig,name):
        recorte='Validação temporal de 2023' if name.startswith('05_') else ('Treino jul/2021-dez/2022' if name.startswith('07_') else 'Teste temporal de 2024')
        fig.text(.01,.012,f'Fonte: CTTU/Prefeitura do Recife. {recorte}; unidade: bairro-mês.',fontsize=8,color='#546874')
        fig.tight_layout(rect=(0,.045,1,.97));fig.savefig(figdir/f'{name}.png');plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(10,8))
    for ax,name in zip(axs.flat,modelids):
        g=test[test.modelo.eq(name)];cm=confusion_matrix(g.alvo,g.predito,labels=[0,1]);ax.imshow(cm,cmap='Blues',vmin=0,vmax=len(g));ax.set_xticks([0,1],['Regular','Elevado']);ax.set_yticks([0,1],['Regular','Elevado']);ax.set_xlabel('Classe predita');ax.set_ylabel('Classe observada');ax.set_title(NAMES[name])
        for (i,j),v in np.ndenumerate(cm):ax.text(j,i,str(v),ha='center',va='center',fontsize=20,color='white' if v>len(g)/2 else '#153448')
    fig.suptitle('Matrizes de confusão | limiares definidos antes do teste');save(fig,'01_matrizes_confusao')
    fig,ax=plt.subplots(figsize=(9,5))
    for name in modelids:
        g=test[test.modelo.eq(name)];fpr,tpr,_=roc_curve(g.alvo,g.score);auc=roc_auc_score(g.alvo,g.score);ax.plot(fpr,tpr,label=f'{NAMES[name]} · AUC={auc:.3f}',color=COLORS[name],lw=2)
    ax.plot([0,1],[0,1],'--',color='#ABB4BB',label='Referência aleatória');ax.set(xlabel='Taxa de falsos positivos',ylabel='Recall (sensibilidade)',title='Curvas ROC no teste temporal de 2024',xlim=(0,1),ylim=(0,1.02));ax.legend(loc='lower right');save(fig,'02_curvas_roc')
    fig,ax=plt.subplots(figsize=(9,5))
    for name in modelids:
        g=test[test.modelo.eq(name)];p,r,_=precision_recall_curve(g.alvo,g.score);ap=average_precision_score(g.alvo,g.score);ax.step(r,p,where='post',label=f'{NAMES[name]} · AP={ap:.3f}',color=COLORS[name],lw=2)
    prev=test[test.modelo.eq('dummy')].alvo.mean();ax.axhline(prev,ls='--',color='#ABB4BB',label=f'Prevalência positiva: {prev:.1%}');ax.set(xlabel='Recall',ylabel='Precisão',title='Curvas precision-recall | AP não é área trapezoidal',xlim=(0,1),ylim=(0,1.03));ax.legend(loc='lower left');save(fig,'03_curvas_precision_recall')
    z=result[result.particao.eq('teste')].set_index('modelo').reindex(modelids)
    fig,ax=plt.subplots(figsize=(10,5));x=np.arange(4);width=.19
    for i,m in enumerate(['acuracia','precisao','recall','f1']):ax.bar(x+(i-1.5)*width,z[m],width,label={'acuracia':'Acurácia','precisao':'Precisão','recall':'Recall','f1':'F1'}[m])
    ax.set_xticks(x,[NAMES[n] for n in modelids]);ax.set(ylim=(0,1.05),ylabel='Métrica (0 a 1)',title='Comparação de métricas no teste temporal');ax.legend(ncol=4);save(fig,'04_comparacao_metricas')
    thresholds=pd.read_csv(out/'tabelas/limiares_validacao.csv');fig,axs=plt.subplots(1,2,figsize=(11,4))
    for ax,name in zip(axs,['logistica','arvore']):
        g=thresholds[thresholds.modelo.eq(name)]
        for m in ['precisao','recall','f1']:ax.plot(g.limiar,g[m],label=m)
        ax.axvline(meta['limiares'][name],ls='--',color='#546874',label=f'Limiar: {meta["limiares"][name]:.2f}');ax.set(xlabel='Limiar do score',ylabel='Métrica na validação 2023',title=NAMES[name],ylim=(0,1.05));ax.legend(fontsize=8)
    fig.suptitle('Trade-off entre alarmes e omissões: escolha somente na validação');save(fig,'05_limiares_validacao')
    fig,ax=plt.subplots(figsize=(11,4))
    monthly=pd.read_csv(out/'tabelas/metricas_mensais_teste.csv')
    for name in modelids:
        g=monthly[monthly.modelo.eq(name)];ax.plot(g.periodo.str[-2:],g.f1,'o-',label=NAMES[name],color=COLORS[name])
    ax.set(xlabel='Mês de 2024',ylabel='F1',ylim=(0,1),title='Estabilidade temporal do desempenho');ax.legend(ncol=2);save(fig,'06_f1_mensal')
    fig,ax=plt.subplots(figsize=(12,6));model=models['arvore'];plot_tree(model.named_steps['modelo'],feature_names=model.named_steps['pre'].get_feature_names_out(),class_names=['Regular','Elevado'],filled=True,rounded=True,ax=ax,fontsize=7,max_depth=2);ax.set_title('Árvore: três primeiros níveis | modelo completo tem profundidade máxima 4');save(fig,'07_arvore_interpretavel')
    win=meta['modelo_selecionado'];g=test[test.modelo.eq(win)]
    errors=g.assign(erro=g.alvo.ne(g.predito)).groupby('bairro').agg(erros=('erro','sum'),positivos=('alvo','sum'),alertas=('predito','sum')).sort_values(['erros','bairro'],ascending=[False,True]).head(12)
    errors.to_csv(out/'tabelas/bairros_mais_erros.csv')
    fig,ax=plt.subplots(figsize=(10,5));z=errors.iloc[::-1];ax.barh(z.index,z.erros,color=COLORS[win]);ax.set(xlabel='Bairro-meses classificados incorretamente (de 12)',ylabel='Bairro',title=f'Onde o modelo selecionado errou mais | {NAMES[win]}');save(fig,'08_erros_bairro')

def export_dashboard(base,bairros,quality,result,preds,meta,root):
    root=Path(root);d=root/'semana_2_dashboard';d.mkdir(exist_ok=True)
    valid=base.loc[base.data_valida].copy();valid['ano']=valid.data_dt.dt.year;valid['mes']=valid.data_dt.dt.month;valid['semana']=valid.data_dt.dt.dayofweek
    # Apenas os campos agregáveis são publicados. Endereços, nomes livres e protocolos ficam fora da interface.
    bidx={b:i for i,b in enumerate(bairros)};types=sorted(base.tipo_chave.dropna().unique().tolist());statuses=sorted(base.situacao_chave.dropna().unique().tolist())
    ti={t:i for i,t in enumerate(types)};si={s:i for i,s in enumerate(statuses)}
    rows=[]
    for r in valid.itertuples():rows.append([int(r.ano),int(r.mes),int(r.semana),int(r.hora_n) if pd.notna(r.hora_n) else -1,bidx.get(r.bairro_chave,-1) if pd.notna(r.bairro_chave) else -1,ti.get(r.tipo_chave,-1) if pd.notna(r.tipo_chave) else -1,si.get(r.situacao_chave,-1) if pd.notna(r.situacao_chave) else -1])
    rawgeo=json.loads((root/'dados/brutos/bairros_oficiais.geojson').read_text());geo=[]
    for f in rawgeo['features']:
        key=prep.chave(f['properties']['EBAIRRNOME'])
        if key not in bidx:raise ValueError('Malha e relação oficial de bairros divergentes: '+key)
        geom=f['geometry'];polys=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
        # Simplificação para visualização, sem atribuir coordenadas pontuais aos chamados.
        rings=[]
        for poly in polys:
            for ring in poly:
                step=max(1,len(ring)//180);pts=ring[::step]
                if pts[-1]!=pts[0]:pts.append(pts[0])
                rings.append([[round(x,6),round(y,6)] for x,y,*_ in pts])
        geo.append({'i':bidx[key],'rings':rings})
    predictions={}
    for name,g in preds[preds.particao.eq('teste')].groupby('modelo'):
        predictions[name]=[[bidx[r.bairro],r.periodo,int(r.chamados),int(r.alvo),float(r.score)] for r in g.itertuples()]
    curves={}
    for name,g in preds[preds.particao.eq('teste')].groupby('modelo'):
        fpr,tpr,_=roc_curve(g.alvo,g.score);p,r,_=precision_recall_curve(g.alvo,g.score)
        curves[name]={'roc':[[round(float(x),6),round(float(y),6)] for x,y in zip(fpr,tpr)],'pr':[[round(float(x),6),round(float(y),6)] for x,y in zip(r,p)]}
    metricsjson=json.loads(result[result.particao.eq('teste')].to_json(orient='records'))
    obj={'meta':meta,'bairro':bairros,'tipo':types,'situacao':statuses,'records':rows,'geo':geo,
        'predictions':predictions,'curves':curves,'metrics':metricsjson,
        'quality':json.loads(quality.to_json(orient='records')),'totais':{'brutos':len(base),'datados':len(valid),'bairro_validado':int(base.bairro_validado.sum())}}
    dump(d/'dados_dashboard.json',obj)
    return obj

def executar(root=None):
    root=Path(root or Path(__file__).resolve().parent)
    base,bairros,quality=carregar(root);panel,corte=painel_mensal(base,bairros)
    out=root/'semana_1_classificadores';out.mkdir(exist_ok=True)
    result,preds,meta,models=treinar(panel,corte,out)
    figuras(result,preds,meta,models,out)
    dashboard=export_dashboard(base,bairros,quality,result,preds,meta,root)
    env={'python':platform.python_version(),'versoes':{m:importlib.metadata.version(m) for m in ['numpy','pandas','scipy','scikit-learn','matplotlib','requests']}}
    dump(root/'ambiente.json',env)
    checks={'dez_csvs':True,'registros_brutos':len(base),'painel_sem_chaves_repetidas':not panel.duplicated(['bairro','periodo']).any(),
        'lag1_conferido_com_historico':True,'particoes_temporais_sem_sobreposicao':True,'limiar_escolhido_somente_validacao':True,
        'features_sem_alvo_ou_dados_mes_corrente':True,'soma_matrizes_igual_ao_teste':bool(result[result.particao.eq('teste')].apply(lambda r:r.tn+r.fp+r.fn+r.tp==r.n,axis=1).all()),
        'graficos_semana1':len(list((out/'graficos').glob('*.png'))),'registros_dashboard':len(dashboard['records'])}
    dump(root/'verificacoes_analise.json',checks)
    print(quality.to_string(index=False));print('\nCORTE',corte,'MODELO',meta['modelo_selecionado']);print(result.to_string(index=False))
    return base,panel,result,preds,meta,quality

if __name__=='__main__':executar()
