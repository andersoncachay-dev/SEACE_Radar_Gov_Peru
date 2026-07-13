
from typing import Tuple, List
import time
import re
from urllib.parse import urljoin
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
BASE_URL = "https://prod2.seace.gob.pe"
PROCESS_FORM = "tbBuscador:idFormBuscarProceso"

STAGE_MAP = {
    'convocatoria': ('convocatoria_inicio','convocatoria_fin'),
    'registro de participantes': ('registro_inicio','registro_fin'),
    'formulacion de consultas': ('consulta_inicio','consulta_fin'),
    'formulacion de consultas y observaciones': ('consulta_inicio','consulta_fin'),
    'absolucion de consultas': ('absolucion_inicio','absolucion_fin'),
    'absolucion de consultas y observaciones': ('absolucion_inicio','absolucion_fin'),
    'integracion de las bases': ('integracion_inicio','integracion_fin'),
    'presentacion de propuestas': ('propuesta_inicio','propuesta_fin'),
    'calificacion y evaluacion de propuestas': ('evaluacion_inicio','evaluacion_fin'),
    'otorgamiento de la buena pro': ('buena_pro_inicio','buena_pro_fin'),
}


def _version_value(version: str) -> str:
    text=str(version or '').lower()
    if '3' in text: return '3'
    if '2' in text: return '2'
    return str(version or '')


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(s: str) -> str:
    return _clean_text(s).lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n')


def _set_input_like_user(driver, element_id: str, value: str) -> bool:
    try:
        el=driver.find_element(By.ID, element_id)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.2)
        try:
            el.click(); el.send_keys(Keys.CONTROL,'a'); el.send_keys(Keys.BACKSPACE); el.send_keys(str(value))
        except Exception: pass
        driver.execute_script("""
            const el=document.getElementById(arguments[0]);
            if(el){el.value=arguments[1]; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true}));}
        """, element_id, str(value))
        return True
    except Exception: return False


def _click_like_user(driver, element_id: str) -> bool:
    try:
        el=WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.ID,element_id)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el); time.sleep(0.5)
        try: ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
        except Exception: driver.execute_script("arguments[0].click();", el)
        return True
    except Exception: return False


def _looks_like_data_row(cells: List[str]) -> bool:
    if not cells or len(cells)<8: return False
    if not re.fullmatch(r"\d{1,3}", cells[0]): return False
    text=_norm(' '.join(cells))
    return any(t in text for t in ['satelital','san gaban','marina de guerra','bcrp','fuerza aerea','geofisico','ejercito','ucayali','apurimac'])


def _extract_url_from_html_fragment(html: str):
    if 'fichaSeleccion' not in html: return ''
    m=re.search(r"(\/seacebus-uiwd-pub\/fichaSeleccion\/fichaSeleccion\.xhtml[^'\"\s)<>]+)", html)
    if m: return urljoin(BASE_URL, m.group(1))
    m=re.search(r"(fichaSeleccion\/fichaSeleccion\.xhtml[^'\"\s)<>]+)", html)
    if m: return urljoin(BASE_URL+'/seacebus-uiwd-pub/', m.group(1))
    return ''


def _extract_url_from_tr(tr):
    for a in tr.find_all('a'):
        href=a.get('href') or ''
        onclick=a.get('onclick') or ''
        data=href+' '+onclick
        url=_extract_url_from_html_fragment(data)
        if url: return url
        if 'fichaSeleccion' in href and href!='#': return urljoin(BASE_URL, href)
    return _extract_url_from_html_fragment(str(tr))


def _row_to_dict(cells: List[str], detail_url: str='') -> dict:
    cells=[_clean_text(c) for c in cells if _clean_text(c)]
    if len(cells)>=10 and cells[5].lower() in ['bien','servicio','obra','consultoría de obra','consultoria de obra']:
        n,entidad,fecha,nomen,reiniciado,objeto,desc,monto,moneda,version=cells[:10]
        acciones=cells[10] if len(cells)>10 else ''
    elif len(cells)>=9:
        n,entidad,fecha,nomen,objeto,desc,monto,moneda,version=cells[:9]
        reiniciado=''; acciones=cells[9] if len(cells)>9 else ''
    else: return {}
    base={'N°':n,'RUC':'','Nombre o Sigla de la Entidad':entidad,'Fecha y Hora de Publicacion':fecha,'Nomenclatura':nomen,'Reiniciado Desde':reiniciado,'Objeto de Contratación':objeto,'Descripción de Objeto':desc,'Código SNIP':'','Código Único de Inversión':'','VR / VE / Cuantía de la contratación':monto,'Moneda':moneda,'Versión SEACE':version,'Estado Comercial':'','Vigencia':'','Dirección Legal':'','Teléfono de la Entidad':'','Acciones':acciones,'url_detalle':detail_url}
    for c in ['convocatoria_inicio','convocatoria_fin','registro_inicio','registro_fin','consulta_inicio','consulta_fin','absolucion_inicio','absolucion_fin','integracion_inicio','integracion_fin','propuesta_inicio','propuesta_fin','evaluacion_inicio','evaluacion_fin','buena_pro_inicio','buena_pro_fin']:
        base[c]=''
    return base


def _parse_primefaces_grid(html: str):
    soup=BeautifulSoup(html,'html.parser')
    rows=[]
    for tr in soup.find_all('tr'):
        cells=[_clean_text(td.get_text(' ',strip=True)) for td in tr.find_all(['td','th'])]
        cells=[c for c in cells if c]
        if _looks_like_data_row(cells): rows.append((cells,_extract_url_from_tr(tr)))
    clean_rows=[r for r in rows if 8<=len(r[0])<=13 and re.fullmatch(r"\d{1,3}",r[0][0])]
    if clean_rows: rows=clean_rows
    data=[]
    for cells,url in rows:
        d=_row_to_dict(cells,url)
        if d: data.append(d)
    dedup=[]; seen=set()
    for d in data:
        key=(d.get('N°'),d.get('Nomenclatura'),d.get('Nombre o Sigla de la Entidad'))
        if key not in seen: seen.add(key); dedup.append(d)
    return pd.DataFrame(dedup), [r[0] for r in rows[:5]]


def _parse_tables(html:str):
    with open('debug_browser.html','w',encoding='utf-8',errors='ignore') as f: f.write(html)
    df2,sample=_parse_primefaces_grid(html)
    if not df2.empty: return df2,0,[('primefaces_rows',len(df2),len(df2.columns),sample)]
    try: tables=pd.read_html(html)
    except Exception: tables=[]
    return pd.DataFrame(),len(tables),[]


def _normalize(df):
    if df.empty: return df
    if isinstance(df.columns,pd.MultiIndex): df.columns=[' '.join(str(x) for x in col if str(x)!='nan').strip() for col in df.columns]
    df=df.copy(); df.columns=[' '.join(str(c).split()) for c in df.columns]
    return df


def _parse_any_datetime(text:str):
    if not text: return ''
    m=re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})(?:\s+(\d{1,2}:\d{2}))?", text)
    if not m: return ''
    return (m.group(1)+' '+m.group(2)) if m.group(2) else m.group(1)


def _is_probably_bad_nomen(value: str) -> bool:
    v=_norm(value)
    bad=['entidad convocante','tipo compra','n convocatoria','version seace','informacion general','objeto de contratacion']
    return (not v) or any(b in v for b in bad) or len(v)<8


def _parse_key_value_pairs(soup):
    pairs=[]
    for tr in soup.find_all('tr'):
        cells=[_clean_text(td.get_text(' ',strip=True)) for td in tr.find_all(['td','th'])]
        cells=[c for c in cells if c]
        if len(cells)>=2:
            for i in range(0,len(cells)-1,2): pairs.append((cells[i],cells[i+1]))
            pairs.append((cells[0],cells[1]))
    return pairs


def _stage_key(etapa:str):
    e=_norm(etapa)
    for k,v in STAGE_MAP.items():
        if k in e: return v
    return None


def _parse_cronograma(soup):
    chron=[]
    for tr in soup.find_all('tr'):
        cells=[_clean_text(td.get_text(' ',strip=True)) for td in tr.find_all(['td','th'])]
        cells=[c for c in cells if c]
        if len(cells)>=3:
            etapa=cells[0]
            key=_stage_key(etapa)
            if key:
                inicio=_parse_any_datetime(cells[-2])
                fin=_parse_any_datetime(cells[-1])
                chron.append({'Etapa':etapa,'Fecha Inicio':inicio,'Fecha Fin':fin})
    # dedup by stage
    out=[]; seen=set()
    for r in chron:
        k=_norm(r['Etapa'])
        if k not in seen:
            seen.add(k); out.append(r)
    return out


def _parse_detail_page(html: str, expected_nomen: str='') -> dict:
    soup=BeautifulSoup(html,'html.parser')
    full=_clean_text(soup.get_text(' ',strip=True))
    info={'RUC':'','Dirección Legal':'','Teléfono de la Entidad':'','Nomenclatura Detalle':'','Detalle Contiene Nomenclatura':False,'cronograma':[]}
    for c in ['convocatoria_inicio','convocatoria_fin','registro_inicio','registro_fin','consulta_inicio','consulta_fin','absolucion_inicio','absolucion_fin','integracion_inicio','integracion_fin','propuesta_inicio','propuesta_fin','evaluacion_inicio','evaluacion_fin','buena_pro_inicio','buena_pro_fin']:
        info[c]=''
    expected_norm=_norm(expected_nomen); full_norm=_norm(full)
    if expected_norm and expected_norm in full_norm:
        info['Detalle Contiene Nomenclatura']=True; info['Nomenclatura Detalle']=expected_nomen
    for label,value in _parse_key_value_pairs(soup):
        lab=_norm(label).replace(':',''); val=_clean_text(value)
        if 'nomenclatura' in lab and not _is_probably_bad_nomen(val): info['Nomenclatura Detalle']=val
        if ('n ruc' in lab or 'ruc'==lab or 'n° ruc' in lab or 'nº ruc' in lab) and re.search(r'\d{11}',val): info['RUC']=re.search(r'\d{11}',val).group(0)
        if 'direccion legal' in lab: info['Dirección Legal']=val
        if 'telefono de la entidad' in lab: info['Teléfono de la Entidad']=val
    if not info['RUC']:
        m=re.search(r"N[°º]?\s*Ruc\s+(\d{11})",full,re.IGNORECASE) or re.search(r"\b(20\d{9}|10\d{9})\b",full)
        if m: info['RUC']=m.group(1)
    cron=_parse_cronograma(soup)
    info['cronograma']=cron
    for row in cron:
        keys=_stage_key(row['Etapa'])
        if keys:
            info[keys[0]]=row['Fecha Inicio']
            info[keys[1]]=row['Fecha Fin']
    if _is_probably_bad_nomen(info.get('Nomenclatura Detalle','')) and info['Detalle Contiene Nomenclatura']:
        info['Nomenclatura Detalle']=expected_nomen
    return info


def _to_dt(v):
    if not v: return pd.NaT
    return pd.to_datetime(v, dayfirst=True, errors='coerce')


def _dias_hasta(v, now=None):
    dt=_to_dt(v)
    if pd.isna(dt): return ''
    now=now or pd.Timestamp.now()
    return int((dt.normalize()-now.normalize()).days)


def _infer_estado_cron(row):
    now=pd.Timestamp.now()
    consulta_fin=row.get('consulta_fin','') or row.get('Consulta Fin','')
    propuesta_fin=row.get('propuesta_fin','') or row.get('Propuesta Fin','')
    buena_fin=row.get('buena_pro_fin','') or row.get('Buena Pro Fin','')
    cf=_to_dt(consulta_fin); pf=_to_dt(propuesta_fin); bf=_to_dt(buena_fin)
    if pd.notna(cf) and now <= cf:
        return 'Vigente para Consultas y Propuesta','🟢'
    if pd.notna(pf) and now <= pf:
        return 'Vigente sólo para Propuesta','🟡'
    if pd.notna(bf) and now >= bf:
        return 'Cerrado','🔴'
    if pd.notna(pf) and now > pf:
        return 'En Evaluación','🟠'
    # fallback for rows without cronograma
    nomen=str(row.get('Nomenclatura','') or row.get('nomenclatura','')).upper()
    try: m=float(str(row.get('VR / VE / Cuantía de la contratación',0) or row.get('monto',0)).replace(',',''))
    except Exception: m=0
    if 'RES-PROC' in nomen or m>0: return 'Revisar','🟠'
    return 'Vigente para Consultas y Propuesta','🟢'


def _find_exact_row_action(driver,row_no,nomenclatura):
    js=r"""
    const rowNo=String(arguments[0]).trim(); const nomen=String(arguments[1]).trim();
    function clean(t){return (t||'').replace(/\s+/g,' ').trim();}
    const trs=Array.from(document.querySelectorAll('tr'));
    for(const tr of trs){
      const cells=Array.from(tr.querySelectorAll('td,th')).map(td=>clean(td.innerText));
      if(cells.length<8) continue; if(cells[0]!==rowNo) continue; if(!cells.some(c=>c.includes(nomen))) continue;
      const clickables=Array.from(tr.querySelectorAll('a,button,img,span.ui-icon'));
      if(clickables.length===0) return null;
      for(let i=clickables.length-1;i>=0;i--){
        const el=clickables[i];
        const txt=clean((el.innerText||'')+' '+(el.getAttribute('title')||'')+' '+(el.getAttribute('alt')||'')+' '+(el.getAttribute('href')||'')+' '+(el.getAttribute('onclick')||'')+' '+(el.className||''));
        const low=txt.toLowerCase();
        if(low.includes('detalle')||low.includes('fichaseleccion')||low.includes('ver')||low.includes('consultar')||low.includes('ui-icon-search')||low.includes('fa-search')||low.includes('lupa')) return el;
      }
      const lastCell=tr.querySelector('td:last-child');
      if(lastCell){const lastClicks=Array.from(lastCell.querySelectorAll('a,button,img,span.ui-icon')); if(lastClicks.length>0) return lastClicks[lastClicks.length-1];}
      return clickables[clickables.length-1];
    }
    return null;
    """
    try: return driver.execute_script(js,str(row_no),nomenclatura)
    except Exception: return None


def _apply_if_valid(df,idx,row,info,diagnostics):
    target=_norm(row.get('Nomenclatura','')); got=_norm(info.get('Nomenclatura Detalle','')); contains=bool(info.get('Detalle Contiene Nomenclatura'))
    if target and not contains and got and target not in got and got not in target:
        diagnostics.append(f"Detalle descartado fila {idx}: nomenclatura no coincide. grilla={row.get('Nomenclatura','')} / ficha={info.get('Nomenclatura Detalle','')}")
        return False
    if target and not contains and not got:
        diagnostics.append(f"Detalle descartado fila {idx}: no se pudo validar nomenclatura. grilla={row.get('Nomenclatura','')}")
        return False
    for k in ['RUC','Dirección Legal','Teléfono de la Entidad']:
        if info.get(k): df.at[idx,k]=info[k]
    for k in ['convocatoria_inicio','convocatoria_fin','registro_inicio','registro_fin','consulta_inicio','consulta_fin','absolucion_inicio','absolucion_fin','integracion_inicio','integracion_fin','propuesta_inicio','propuesta_fin','evaluacion_inicio','evaluacion_fin','buena_pro_inicio','buena_pro_fin']:
        if info.get(k): df.at[idx,k]=info[k]
    estado,vig=_infer_estado_cron(df.loc[idx])
    df.at[idx,'Estado Comercial']=estado; df.at[idx,'Vigencia']=vig
    dias_consulta = _dias_hasta(df.at[idx,'consulta_fin'])
    dias_propuesta = _dias_hasta(df.at[idx,'propuesta_fin'])

    df.at[idx,'dias_para_consulta'] = (
        str(dias_consulta) if dias_consulta != '' else ''
    )

    df.at[idx,'dias_para_propuesta'] = (
        str(dias_propuesta) if dias_propuesta != '' else ''
    )
    # Save compact cronograma text for Excel audit
    if info.get('cronograma'):
        df.at[idx,'cronograma_texto']=' | '.join([f"{r['Etapa']}: {r['Fecha Inicio']} -> {r['Fecha Fin']}" for r in info['cronograma']])
    return True


def _enrich_details(driver,df,max_details,diagnostics):
    reviewed=0; applied=0
    for idx,row in df.head(max_details).iterrows():
        nomen=row.get('Nomenclatura',''); row_no=row.get('N°',''); url=row.get('url_detalle','')
        try:
            before=set(driver.window_handles)
            if url:
                diagnostics.append(f"Detalle URL fila {idx}: {url}"); driver.get(url)
            else:
                action=_find_exact_row_action(driver,row_no,nomen)
                if action is None:
                    diagnostics.append(f"Sin acción detalle exacta para fila {idx} / N={row_no} / {nomen}")
                    estado,vig=_infer_estado_cron(row); df.at[idx,'Estado Comercial']=estado; df.at[idx,'Vigencia']=vig; continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});",action); time.sleep(0.3)
                try: ActionChains(driver).move_to_element(action).pause(0.1).click(action).perform()
                except Exception: driver.execute_script("arguments[0].click();",action)
                time.sleep(2)
                new=list(set(driver.window_handles)-before)
                if new: driver.switch_to.window(new[-1])
            if 'fichaSeleccion' in driver.current_url:
                df.at[idx,'url_detalle']=driver.current_url
            time.sleep(2)
            info=_parse_detail_page(driver.page_source,expected_nomen=nomen)
            diagnostics.append(f"Fila {idx} cronograma: esperado={nomen} / contiene={info.get('Detalle Contiene Nomenclatura')} / ruc={info.get('RUC','')} / consulta_fin={info.get('consulta_fin','')} / propuesta_fin={info.get('propuesta_fin','')} / buena_fin={info.get('buena_pro_fin','')}")
            reviewed+=1
            if _apply_if_valid(df,idx,row,info,diagnostics): applied+=1
            if len(driver.window_handles)>1:
                driver.close(); driver.switch_to.window(driver.window_handles[0])
            else: driver.back()
            time.sleep(2)
        except Exception as e:
            diagnostics.append(f"No se pudo enriquecer cronograma fila {idx} / {nomen}: {type(e).__name__} - {e}")
            try:
                if len(driver.window_handles)>1:
                    driver.close(); driver.switch_to.window(driver.window_handles[0])
                else: driver.back()
            except Exception: pass
            estado,vig=_infer_estado_cron(row); df.at[idx,'Estado Comercial']=estado; df.at[idx,'Vigencia']=vig
    diagnostics.append(f"Cronogramas revisados: {reviewed}/{min(max_details,len(df))}; aplicados correctamente: {applied}")
    return df


def search_seace_public_browser(url=SEACE_PUBLIC_URL,keyword='satelital',year='2026',version='Seace 3',headless=False,max_wait=45,enrich_details=False,max_details=10)->Tuple[pd.DataFrame,List[str]]:
    diagnostics=[]; options=Options()
    if headless: options.add_argument('--headless=new')
    options.add_argument('--start-maximized'); options.add_argument('--disable-notifications'); options.add_argument('--disable-popup-blocking'); options.add_argument('--ignore-certificate-errors')
    options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    driver=None
    try:
        driver=webdriver.Chrome(options=options); wait=WebDriverWait(driver,max_wait); driver.get(url); diagnostics.append(f"GET navegador: {url}")
        time.sleep(3); tabs=driver.find_elements(By.XPATH,"//*[contains(text(),'Buscador de Procedimientos de Selección')]")
        if tabs: driver.execute_script("arguments[0].click();",tabs[0]); diagnostics.append('Pestaña Procedimientos seleccionada'); time.sleep(3)
        desc_id=f"{PROCESS_FORM}:descripcionObjeto"; wait.until(EC.presence_of_element_located((By.ID,desc_id)))
        driver.execute_script("const active=document.getElementById('tbBuscador_activeIndex'); if(active) active.value='1';")
        ok_desc=_set_input_like_user(driver,desc_id,keyword); ok_year=_set_input_like_user(driver,f"{PROCESS_FORM}:anioConvocatoria_input",str(year)); _set_input_like_user(driver,f"{PROCESS_FORM}:anioConvocatoria_focus",str(year)); ok_ver=_set_input_like_user(driver,f"{PROCESS_FORM}:j_idt247_input",_version_value(version))
        diagnostics += [f"Descripción seteada: {ok_desc} -> {keyword}", f"Año seteado: {ok_year} -> {year}", f"Versión seteada: {ok_ver} -> {_version_value(version)}"]
        clicked=False
        for bid in [f"{PROCESS_FORM}:btnBuscarSelToken",f"{PROCESS_FORM}:btnBuscarSel"]:
            if _click_like_user(driver,bid): diagnostics.append(f"Click botón: {bid}"); clicked=True; break
        if not clicked: diagnostics.append('No se encontró botón Buscar por ID; intentando submit del formulario'); driver.execute_script("document.getElementById(arguments[0]).submit();",PROCESS_FORM)
        end=time.time()+max_wait; last_len=0; best_info=[]
        while time.time()<end:
            time.sleep(1); html=driver.page_source
            if len(html)!=last_len: last_len=len(html); diagnostics.append(f"HTML len actual: {last_len}")
            df,tables_count,candidates_info=_parse_tables(html); best_info=candidates_info
            if not df.empty:
                with open('respuesta_seace_browser.html','w',encoding='utf-8',errors='ignore') as f: f.write(html)
                df=_normalize(df)
                for col in [
                    'RUC',
                    'Estado Comercial',
                    'Vigencia',
                    'Dirección Legal',
                    'Teléfono de la Entidad',
                    'cronograma_texto'
                ]:
                    if col not in df.columns:
                        df[col] = ''

                if 'dias_para_consulta' not in df.columns:
                    df['dias_para_consulta'] = ''

                if 'dias_para_propuesta' not in df.columns:
                    df['dias_para_propuesta'] = ''
                for col in ['convocatoria_inicio','convocatoria_fin','registro_inicio','registro_fin','consulta_inicio','consulta_fin','absolucion_inicio','absolucion_fin','integracion_inicio','integracion_fin','propuesta_inicio','propuesta_fin','evaluacion_inicio','evaluacion_fin','buena_pro_inicio','buena_pro_fin']:
                    if col not in df.columns: df[col]=''
                if enrich_details:
                    diagnostics.append(f"Enriqueciendo cronogramas para máximo {max_details} procesos...")
                    df=_enrich_details(driver,df,max_details,diagnostics)
                for idx,row in df.iterrows():
                    estado,vig=_infer_estado_cron(row); df.at[idx,'Estado Comercial']=estado; df.at[idx,'Vigencia']=vig
                    dias_consulta = _dias_hasta(
                        row.get('consulta_fin','')
                    )

                    dias_propuesta = _dias_hasta(
                        row.get('propuesta_fin','')
                    )

                    df.at[idx,'dias_para_consulta'] = (
                        str(dias_consulta) if dias_consulta != '' else ''
                    )

                    df.at[idx,'dias_para_propuesta'] = (
                        str(dias_propuesta) if dias_propuesta != '' else ''
                    )
                diagnostics.append(f"Tablas HTML detectadas: {tables_count}"); diagnostics.append(f"Candidatas: {candidates_info}"); diagnostics.append(f"Tabla detectada navegador: {len(df)} filas / {len(df.columns)} columnas")
                return df,diagnostics
        html=driver.page_source
        with open('respuesta_seace_browser.html','w',encoding='utf-8',errors='ignore') as f: f.write(html)
        df,tables_count,candidates_info=_parse_tables(html); diagnostics.append(f"Tablas HTML al final: {tables_count}"); diagnostics.append(f"Candidatas al final: {candidates_info or best_info}"); diagnostics.append('No se detectó tabla con navegador.')
        return pd.DataFrame(),diagnostics
    except Exception as e:
        diagnostics.append(f"Error navegador: {type(e).__name__} - {e}"); return pd.DataFrame(),diagnostics
    finally:
        try:
            if driver: driver.quit()
        except Exception: pass
