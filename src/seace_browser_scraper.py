
from typing import Callable, Tuple, List
import os
import time
import re
from urllib.parse import urljoin
import pandas as pd
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException

from .proxy_utils import build_chrome_driver

SEACE_PUBLIC_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
BASE_URL = "https://prod2.seace.gob.pe"
PROCESS_FORM = "tbBuscador:idFormBuscarProceso"
SEACE_DEBUG_HTML = os.getenv("SEACE_DEBUG_HTML", "false").lower() == "true"


def _write_debug_html(filename: str, html: str) -> None:
    if not SEACE_DEBUG_HTML:
        return
    with open(filename, "w", encoding="utf-8", errors="ignore") as file:
        file.write(html)

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


def _selection_parts(nomenclature: str) -> tuple[str, str]:
    """Split SEACE nomenclature into selection number and call number."""
    value = _clean_text(nomenclature)
    match = re.match(r"^[A-Z]+(?:-[A-Z]+)+-(\d+)-\d{4}-.+-(\d+)$", value, re.IGNORECASE)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r"^(.*)-(\d+)$", value)
    return (match.group(1), match.group(2)) if match else (value, "")


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


def _set_select_value(driver, element_id: str, value: str) -> bool:
    try:
        return bool(driver.execute_script("""
            const el=document.getElementById(arguments[0]);
            if(!el) return false;
            el.value=arguments[1];
            el.dispatchEvent(new Event('change',{bubbles:true}));
            return el.value===arguments[1];
        """, element_id, str(value)))
    except Exception:
        return False


def _looks_like_data_row(cells: List[str]) -> bool:
    if not cells or len(cells)<8: return False
    if not re.fullmatch(r"\d{1,3}", cells[0]): return False
    # Result rows are identified by their ordinal and shape.  The previous
    # implementation also required one of a handful of customer keywords,
    # silently discarding valid procedures (for example connectivity tenders).
    return len(cells) >= 8


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
    clean_rows=[r for r in rows if len(r[0])>=8 and re.fullmatch(r"\d{1,3}",r[0][0])]
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
    _write_debug_html("debug_browser.html", html)
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


def _enrich_details(driver,df,max_details,diagnostics,progress_callback=None,cancel_callback=None,target_nomenclatures=None):
    reviewed=0; applied=0
    detail_rows=df
    target_keys={_norm(value) for value in (target_nomenclatures or []) if _norm(value)}
    if target_keys:
        matching=df[df['Nomenclatura'].map(_norm).isin(target_keys)]
        remaining=df.drop(index=matching.index)
        detail_rows=pd.concat([matching,remaining])
    detail_rows=detail_rows.head(max_details)
    total_details=max(1,len(detail_rows))
    for position,(idx,row) in enumerate(detail_rows.iterrows(),start=1):
        if cancel_callback: cancel_callback()
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
            if cancel_callback: cancel_callback()
            diagnostics.append(f"No se pudo enriquecer cronograma fila {idx} / {nomen}: {type(e).__name__} - {e}")
            try:
                if len(driver.window_handles)>1:
                    driver.close(); driver.switch_to.window(driver.window_handles[0])
                else: driver.back()
            except Exception: pass
            estado,vig=_infer_estado_cron(row); df.at[idx,'Estado Comercial']=estado; df.at[idx,'Vigencia']=vig
        if progress_callback: progress_callback(position/total_details,f"Revisando cronograma {position} de {total_details}")
    diagnostics.append(f"Cronogramas revisados: {reviewed}/{min(max_details,len(df))}; aplicados correctamente: {applied}")
    return df


def search_seace_public_browser(url=SEACE_PUBLIC_URL,keyword='satelital',nomenclature='',year='2026',version='Seace 3',headless=False,max_wait=45,enrich_details=False,max_details=10,target_nomenclatures=None,progress_callback: Callable[[float,str],None] | None=None,cancel_callback: Callable[[],None] | None=None)->Tuple[pd.DataFrame,List[str]]:
    diagnostics=[]; options=Options()
    if headless: options.add_argument('--headless=new')
    options.add_argument('--start-maximized'); options.add_argument('--disable-notifications'); options.add_argument('--disable-popup-blocking'); options.add_argument('--ignore-certificate-errors')
    options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    driver=None
    try:
        if cancel_callback: cancel_callback()
        if progress_callback: progress_callback(0.05,"Abriendo SEACE")
        driver=build_chrome_driver(options); wait=WebDriverWait(driver,max_wait); driver.get(url); diagnostics.append(f"GET navegador: {url}")
        time.sleep(3); tabs=driver.find_elements(By.XPATH,"//*[contains(text(),'Buscador de Procedimientos de Selección')]")
        if tabs: driver.execute_script("arguments[0].click();",tabs[0]); diagnostics.append('Pestaña Procedimientos seleccionada'); time.sleep(3)
        desc_id=f"{PROCESS_FORM}:descripcionObjeto"; wait.until(EC.presence_of_element_located((By.ID,desc_id)))
        driver.execute_script("const active=document.getElementById('tbBuscador_activeIndex'); if(active) active.value='1';")
        search_nomen=_clean_text(nomenclature)
        selection_number, call_number=_selection_parts(search_nomen)
        # "Tipo de Selección" is intentionally left as "[Seleccione]". SEACE now
        # lists several near-duplicate labels for the same prefix (e.g. "Concurso
        # Público Abreviado" vs "... Séptima DCF Ley N°32069") that vary by which
        # law governs the record, so guessing one from the nomenclature prefix
        # picks the wrong variant and the search silently returns zero rows.
        # Nro. Selección + Nro. Convocatoria + Año already identify the record
        # uniquely, matching the working manual search.
        ok_desc=True if search_nomen else _set_input_like_user(driver,desc_id,keyword)
        ok_nomen=_set_input_like_user(driver,f"{PROCESS_FORM}:numeroSeleccion",selection_number) if search_nomen else True
        ok_call=_set_input_like_user(driver,f"{PROCESS_FORM}:numeroConvocatoria",call_number) if call_number else True
        ok_year=_set_input_like_user(driver,f"{PROCESS_FORM}:anioConvocatoria_input",str(year)); _set_input_like_user(driver,f"{PROCESS_FORM}:anioConvocatoria_focus",str(year)); ok_ver=_set_input_like_user(driver,f"{PROCESS_FORM}:j_idt247_input",_version_value(version))
        diagnostics += [f"Descripción seteada: {ok_desc} -> {'' if search_nomen else keyword}", f"Número de selección seteado: {ok_nomen} -> {selection_number}", f"Convocatoria seteada: {ok_call} -> {call_number}", f"Año seteado: {ok_year} -> {year}", f"Versión seteada: {ok_ver} -> {_version_value(version)}"]
        clicked=False
        # Use the visible token button so SEACE can populate its anti-bot token
        # before invoking the hidden PrimeFaces submit action.
        if _click_like_user(driver,f"{PROCESS_FORM}:btnBuscarSelToken"):
            diagnostics.append(f"Click botón token: {PROCESS_FORM}:btnBuscarSelToken"); clicked=True
        if not clicked:
            submit_id=f"{PROCESS_FORM}:btnBuscarSel"
            try:
                submit=driver.find_element(By.ID,submit_id)
                driver.execute_script("arguments[0].click();",submit)
                diagnostics.append(f"Click botón PrimeFaces: {submit_id}")
                clicked=True
            except Exception:
                pass
        if not clicked: diagnostics.append('No se encontró botón Buscar por ID; intentando submit del formulario'); driver.execute_script("document.getElementById(arguments[0]).submit();",PROCESS_FORM)
        if progress_callback: progress_callback(0.2,"Esperando resultados de SEACE")
        end=time.time()+max_wait; last_len=0; best_info=[]
        while time.time()<end:
            if cancel_callback: cancel_callback()
            time.sleep(1); html=driver.page_source
            if len(html)!=last_len: last_len=len(html); diagnostics.append(f"HTML len actual: {last_len}")
            df,tables_count,candidates_info=_parse_tables(html); best_info=candidates_info
            if not df.empty:
                if progress_callback: progress_callback(0.4,f"{len(df)} procesos detectados en SEACE")
                _write_debug_html("respuesta_seace_browser.html", html)
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
                    df=_enrich_details(driver,df,max_details,diagnostics,lambda value,message: progress_callback(0.4+value*0.55,message) if progress_callback else None,cancel_callback,target_nomenclatures or ([search_nomen] if search_nomen else None))
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
                if progress_callback: progress_callback(1.0,"Consulta SEACE completada")
                return df,diagnostics
        html=driver.page_source
        _write_debug_html("respuesta_seace_browser.html", html)
        df,tables_count,candidates_info=_parse_tables(html); diagnostics.append(f"Tablas HTML al final: {tables_count}"); diagnostics.append(f"Candidatas al final: {candidates_info or best_info}"); diagnostics.append('No se detectó tabla con navegador.')
        return pd.DataFrame(),diagnostics
    except Exception as e:
        if cancel_callback: cancel_callback()
        diagnostics.append(f"Error navegador: {type(e).__name__} - {e}"); return pd.DataFrame(),diagnostics
    finally:
        try:
            if driver: driver.quit()
        except Exception: pass


_NO_RESULTS_MARKER = 'No se encontraron Datos'
# The search page always renders other tabs' empty tables (e.g. the ACF
# search) with this same "no data" text, regardless of what our own search
# returns. Matching the bare phrase anywhere on the page made the polling
# loop break on that unrelated placeholder before the real AJAX response for
# *our* results table (idFormBuscarProceso:dtProcesos) ever arrived - which
# only showed up as a problem once network latency (e.g. a proxy hop) made
# the real response slower than the first 1-second poll.
_PROCESS_TABLE_NO_RESULTS = re.compile(
    _NO_RESULTS_MARKER + r".{0,300}idFormBuscarProceso:dtProcesos", re.DOTALL
)


def _process_table_has_no_results(html: str) -> bool:
    return bool(_PROCESS_TABLE_NO_RESULTS.search(html))


def _reset_to_search_form(driver, wait, desc_id: str) -> None:
    """Load a clean copy of the process search tab.

    Reused before every target in ``search_seace_public_browser_targets`` so
    one target's leftover AJAX/DOM state (and the extra render lag a proxy
    hop adds) can't produce a stale-element error on the next target.
    """
    driver.get(SEACE_PUBLIC_URL)
    time.sleep(3)
    tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'Buscador de Procedimientos de Selección')]")
    if tabs:
        driver.execute_script("arguments[0].click();", tabs[0])
        time.sleep(3)
    wait.until(EC.presence_of_element_located((By.ID, desc_id)))
    driver.execute_script("const active=document.getElementById('tbBuscador_activeIndex'); if(active) active.value='1';")


# A crashed chromedriver session (proxy-added latency makes this more likely
# over a long-lived session than on a direct connection) fails every command
# on that same driver identically, so continuing to reuse it would silently
# skip every remaining target in one shot. Even short of an outright crash,
# leftover DOM/AJAX state from one target's search made the next target's
# results wrong often enough (stale elements, no matching row) that reusing
# a session at all wasn't worth the saved ~5s of Chrome relaunch time - this
# field feeds a business deadline, so a fresh browser per target is the
# safer default. Each pending target is retried on the next scheduled run
# regardless, so occasional slowness here costs nothing but time.
_TARGETS_PER_BROWSER_SESSION = 1


def _launch_search_driver(options, max_wait: int):
    driver = build_chrome_driver(options)
    wait = WebDriverWait(driver, max_wait)
    desc_id = f"{PROCESS_FORM}:descripcionObjeto"
    _reset_to_search_form(driver, wait, desc_id)
    return driver, wait, desc_id


def _empty_result_columns() -> dict:
    base = {c: '' for c in [
        'RUC','Estado Comercial','Vigencia','Dirección Legal','Teléfono de la Entidad',
        'cronograma_texto','dias_para_consulta','dias_para_propuesta',
    ]}
    for c in ['convocatoria_inicio','convocatoria_fin','registro_inicio','registro_fin','consulta_inicio','consulta_fin','absolucion_inicio','absolucion_fin','integracion_inicio','integracion_fin','propuesta_inicio','propuesta_fin','evaluacion_inicio','evaluacion_fin','buena_pro_inicio','buena_pro_fin']:
        base[c]=''
    return base


def search_seace_public_browser_targets(targets: List[dict], version: str='Seace 3', headless: bool=True, max_wait: int=45, progress_callback: Callable[[float,str],None] | None=None, cancel_callback: Callable[[],None] | None=None) -> Tuple[pd.DataFrame, List[str]]:
    """Fetch the SEACE schedule for a list of already-known opportunities.

    Each target is searched on its own, filling "Descripción del Objeto" with
    that record's own literal description text (falling back to its
    nomenclature) - the same approach a manual search proved reliable with:
    it returns a single matching row. A single broad keyword shared across
    many unrelated processes can return far more rows than the scraper reads
    from the current results page, silently leaving the target out; guessing
    a "Nro. Selección" + "Tipo de Selección" filter is worse, since SEACE now
    lists several near-duplicate "Tipo de Selección" labels for the same
    nomenclature prefix depending on which law governs the record, and
    picking the wrong one returns zero rows. A browser session is reused
    across a handful of targets at a time (see
    ``_TARGETS_PER_BROWSER_SESSION``) to avoid the cost of relaunching Chrome
    per process while still bounding how many targets a single crashed
    session can take down with it.

    Each item in ``targets`` is a dict with ``nomenclature``, ``keyword``
    (the text to type into "Descripción del Objeto") and ``year``.
    """
    diagnostics: List[str] = []; options=Options()
    if headless: options.add_argument('--headless=new')
    options.add_argument('--start-maximized'); options.add_argument('--disable-notifications'); options.add_argument('--disable-popup-blocking'); options.add_argument('--ignore-certificate-errors')
    options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    driver=None; rows: List[dict]=[]
    total=max(1,len(targets))
    try:
        if cancel_callback: cancel_callback()
        if progress_callback: progress_callback(0.02,"Abriendo SEACE")
        diagnostics.append(f"GET navegador: {SEACE_PUBLIC_URL}")
        driver,wait,desc_id=_launch_search_driver(options,max_wait)
        diagnostics.append('Pestaña Procedimientos seleccionada')
        for position,target in enumerate(targets,start=1):
            if position>1 and (position-1)%_TARGETS_PER_BROWSER_SESSION==0:
                try: driver.quit()
                except Exception: pass
                diagnostics.append(f"Reiniciando navegador antes del objetivo {position} (sesión con {_TARGETS_PER_BROWSER_SESSION} objetivos)")
                driver,wait,desc_id=_launch_search_driver(options,max_wait)
            if cancel_callback: cancel_callback()
            nomenclature=_clean_text(target.get('nomenclature'))
            search_text=_clean_text(target.get('keyword') or nomenclature)
            target_year=str(target.get('year') or '')
            if progress_callback: progress_callback((position-1)/total,f"Buscando cronograma {position} de {total}: {nomenclature}")
            if not nomenclature or not search_text:
                diagnostics.append(f"Objetivo omitido (sin nomenclatura o descripción): {target}"); continue
            try:
                _set_input_like_user(driver,desc_id,search_text)
                _set_input_like_user(driver,f"{PROCESS_FORM}:numeroSeleccion",'')
                _set_input_like_user(driver,f"{PROCESS_FORM}:numeroConvocatoria",'')
                _set_input_like_user(driver,f"{PROCESS_FORM}:anioConvocatoria_input",target_year); _set_input_like_user(driver,f"{PROCESS_FORM}:anioConvocatoria_focus",target_year)
                _set_input_like_user(driver,f"{PROCESS_FORM}:j_idt247_input",_version_value(version))
                diagnostics.append(f"Objetivo {nomenclature}: descripción='{search_text[:80]}' año={target_year}")
                clicked=_click_like_user(driver,f"{PROCESS_FORM}:btnBuscarSelToken")
                if not clicked:
                    try:
                        submit=driver.find_element(By.ID,f"{PROCESS_FORM}:btnBuscarSel")
                        driver.execute_script("arguments[0].click();",submit); clicked=True
                    except Exception: pass
                if not clicked:
                    driver.execute_script("document.getElementById(arguments[0]).submit();",PROCESS_FORM)
                # A "no results" reading on the very first poll can be a stale
                # snapshot of dtProcesos taken before the AJAX search response
                # replaced it - more likely with the extra latency of a proxy
                # hop. Require it twice in a row (two poll intervals apart)
                # before trusting it as a genuine empty result.
                end=time.time()+max_wait; df=pd.DataFrame(); poll=0; last_len=0; consecutive_empty=0
                while time.time()<end:
                    if cancel_callback: cancel_callback()
                    time.sleep(1); html=driver.page_source; poll+=1
                    df,_,_=_parse_tables(html)
                    if not df.empty: break
                    if _process_table_has_no_results(html):
                        consecutive_empty+=1
                        diagnostics.append(f"Objetivo {nomenclature}: sondeo {poll} sin filas para dtProcesos (len={len(html)}, consecutivos={consecutive_empty})")
                        if consecutive_empty>=2: break
                    else:
                        consecutive_empty=0
                    last_len=len(html)
                if df.empty:
                    diagnostics.append(f"Objetivo {nomenclature}: SEACE no devolvió filas para esa descripción (sondeos={poll}, ultimo_len={last_len})"); continue
                df=_normalize(df)
                for col,default in _empty_result_columns().items():
                    if col not in df.columns: df[col]=default
                df=_enrich_details(driver,df,1,diagnostics,None,cancel_callback,[nomenclature])
                match=df[df['Nomenclatura'].map(_norm)==_norm(nomenclature)]
                if match.empty:
                    diagnostics.append(f"Objetivo {nomenclature}: la fila exacta no aparece entre los resultados devueltos"); continue
                rows.append(match.iloc[0].to_dict())
                if progress_callback: progress_callback(position/total,f"Cronograma {position} de {total} procesado")
            except Exception as exc:
                if cancel_callback: cancel_callback()
                diagnostics.append(f"Objetivo {nomenclature}: fallo inesperado ({type(exc).__name__}: {exc})")
                try:
                    _reset_to_search_form(driver,wait,desc_id)
                except Exception:
                    # The page-level reset failed too, which usually means the
                    # chromedriver session itself died (proxy hiccup, crash).
                    # Reusing it would fail identically on every remaining
                    # target, so start a completely fresh browser instead.
                    diagnostics.append(f"Objetivo {nomenclature}: sesión del navegador perdida, reiniciando Chrome")
                    try: driver.quit()
                    except Exception: pass
                    try:
                        driver,wait,desc_id=_launch_search_driver(options,max_wait)
                    except Exception as relaunch_exc:
                        diagnostics.append(f"No se pudo reiniciar el navegador: {type(relaunch_exc).__name__} - {relaunch_exc}")
                        break
        return pd.DataFrame(rows), diagnostics
    except Exception as e:
        if cancel_callback: cancel_callback()
        diagnostics.append(f"Error navegador (multi-objetivo): {type(e).__name__} - {e}"); return pd.DataFrame(rows), diagnostics
    finally:
        try:
            if driver: driver.quit()
        except Exception: pass
