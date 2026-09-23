"""Inline CCv2 multi-selection reorder control; no external JavaScript dependency."""
import streamlit as st
from templyfier.english_catalog import TEXT

ORDER_JS = r"""
export default function(component) {
  const {parentElement, data, setTriggerValue} = component;
  const root = parentElement.querySelector('.order-root');
  const selected = new Set();
  const dragCleanups = new Set();
  const originalRows = data.rows.slice();
  let rows = originalRows.slice();
  let dirty = false;
  let anchor = null;
  let dragIds = [];
  const toolbar = document.createElement('div');
  toolbar.className = 'toolbar';
  const status = document.createElement('span');
  status.setAttribute('aria-live','polite');
  const list = document.createElement('div');
  list.className = 'order-list';
  list.setAttribute('aria-label', 'Question order');
  function button(label, action) {
    const b = document.createElement('button'); b.type='button'; b.textContent=label;
    b.onclick=action; return b;
  }
  const save = button('Save order',()=>emit()); save.className='save-order'; save.disabled=true;
  const reset = button('Discard moves',()=>{rows=originalRows.slice();dirty=false;selected.clear();anchor=null;draw();});
  toolbar.append(button('Select all',()=>{rows.forEach(r=>selected.add(r.id));draw();}),
    button('Clear selection',()=>{selected.clear();draw();}),
    button('Move up',()=>nudge(-1)), button('Move down',()=>nudge(1)),reset,save,status);
  root.replaceChildren(toolbar,list);
  function emit(){
    if(!dirty)return;
    save.disabled=true;status.textContent='Saving order...';
    setTriggerValue('reordered',{revision:data.revision, ids:rows.map(r=>r.id)});
  }
  function move(ids, target, after=false) {
    const moving = new Set(ids);
    if(moving.has(target))return;
    const block=rows.filter(r=>moving.has(r.id));
    const rest=rows.filter(r=>!moving.has(r.id));
    let index=target===null?rest.length:rest.findIndex(r=>r.id===target)+(after?1:0);
    if(index<0 || !block.length)return;
    const updated=[...rest.slice(0,index),...block,...rest.slice(index)];
    if(updated.map(r=>r.id).join('\u0000')===rows.map(r=>r.id).join('\u0000'))return;
    rows=updated;dirty=true;draw();
  }
  function nudge(direction){
    if(!selected.size)return;
    let indexes=rows.map((r,i)=>selected.has(r.id)?i:-1).filter(i=>i>=0);
    let target=direction<0?Math.min(...indexes)-1:Math.max(...indexes)+1;
    if(target>=0 && target<rows.length)move([...selected],rows[target].id,direction>0);
  }
  function checkbox(label, ids) {
    const input=document.createElement('input'); input.type='checkbox';
    input.setAttribute('aria-label',label);
    input.checked=ids.every(id=>selected.has(id));
    input.indeterminate=!input.checked && ids.some(id=>selected.has(id));
    input.onchange=()=>{ids.forEach(id=>input.checked?selected.add(id):selected.delete(id));draw();};
    return input;
  }
  function draggable(el, ids, dropId) {
    // The handle owns dragging. Native HTML drag on the parent would cancel
    // movement events before the selection can be dropped.
    el.draggable=false;
    el.ondragstart=e=>{
      ids.forEach(id=>selected.add(id));
      dragIds=rows.filter(r=>selected.has(r.id)).map(r=>r.id);
      e.dataTransfer.effectAllowed='move'; e.dataTransfer.setData('text/plain',JSON.stringify(dragIds));
      status.textContent=`${dragIds.length} question(s) to move`;
    };
    el.ondragover=e=>{
      e.preventDefault();e.dataTransfer.dropEffect='move';
      const after=e.clientY>el.getBoundingClientRect().top+el.offsetHeight/2;
      el.classList.toggle('drop-after',after);el.classList.toggle('drop-before',!after);
      if(e.clientY>list.getBoundingClientRect().bottom-55)list.scrollTop+=22;
      if(e.clientY<list.getBoundingClientRect().top+55)list.scrollTop-=22;
    };
    el.ondragleave=()=>el.classList.remove('drop-before','drop-after');
    el.ondrop=e=>{
      e.preventDefault();e.stopPropagation();
      const after=e.clientY>el.getBoundingClientRect().top+el.offsetHeight/2;
      move(dragIds,dropId,after);
    };
    el.ondragend=()=>list.querySelectorAll('.drop-before,.drop-after').forEach(n=>n.classList.remove('drop-before','drop-after'));
  }
  function handle(ids,label) {
    const h=document.createElement('button');h.type='button';h.className='handle';h.textContent='⠿';
    h.setAttribute('aria-label',`Move ${label}`);h.title='Drag to move the selection';
    let start=null, destination=null, moved=false;
    function cleanup(){
      h.ownerDocument.removeEventListener('mousemove',onMove);
      h.ownerDocument.removeEventListener('mouseup',onUp);
      dragCleanups.delete(cleanup);
    }
    h.onclick=e=>e.stopPropagation();
    h.onmousedown=e=>{
      if(e.button!==0)return;
      e.preventDefault();e.stopPropagation();
      ids.forEach(id=>selected.add(id));dragIds=rows.filter(r=>selected.has(r.id)).map(r=>r.id);
      start={x:e.clientX,y:e.clientY};moved=false;destination=null;
      h.ownerDocument.addEventListener('mousemove',onMove);
      h.ownerDocument.addEventListener('mouseup',onUp,{once:true});
      dragCleanups.add(cleanup);
    };
    function onMove(e){
      if(!start)return;
      if(Math.hypot(e.clientX-start.x,e.clientY-start.y)<5)return;
      moved=true;
      list.querySelectorAll('.drop-before,.drop-after').forEach(n=>n.classList.remove('drop-before','drop-after'));
      const bounds=list.getBoundingClientRect();
      if(e.clientY>bounds.bottom-45)list.scrollTop+=24;
      if(e.clientY<bounds.top+45)list.scrollTop-=24;
      const targets=[...list.querySelectorAll('.question')];
      const target=targets.find(n=>{const r=n.getBoundingClientRect();return e.clientY>=r.top && e.clientY<=r.bottom;});
      if(target){
        const r=target.getBoundingClientRect();const after=e.clientY>r.top+r.height/2;
        destination={id:target.dataset.questionId,after};target.classList.add(after?'drop-after':'drop-before');
      }else if(e.clientY>=list.querySelector('.end').getBoundingClientRect().top){destination={id:null,after:false};}
      status.textContent=`${dragIds.length} question(s) to move`;
    }
    function onUp(e){
      if(!start)return;
      start=null;cleanup();
      if(moved && destination)move(dragIds,destination.id,destination.after);else draw();
    }
    return h;
  }
  function draw(){
    list.replaceChildren();let previousGroup=null;
    rows.forEach((r,index)=>{
      if(r.group && r.group!==previousGroup){
        const members=rows.filter(x=>x.group===r.group).map(x=>x.id);
        const header=document.createElement('div');header.className='group';
        header.append(checkbox(`Select group ${r.groupLabel}`,members),handle(members,`group ${r.groupLabel}`));
        const title=document.createElement('strong');title.textContent=`${r.groupLabel} · ${members.length} items`;
        header.append(title);draggable(header,members,r.id);list.append(header);
      }
      previousGroup=r.group;
      const line=document.createElement('div');line.className='question'+(selected.has(r.id)?' selected':'');
      line.dataset.questionId=r.id;
      line.append(checkbox(`Select ${r.label}`, [r.id]),handle([r.id],r.label));
      const text=document.createElement('span');text.textContent=`${index+1}. ${r.label}`;line.append(text);
      const type=document.createElement('small');type.textContent=r.type+(r.keep?'':' · excluded');line.append(type);
      line.onclick=e=>{
        if(e.target.tagName==='INPUT' || e.target.tagName==='BUTTON')return;
        if(e.shiftKey && anchor!==null){
          rows.slice(Math.min(anchor,index),Math.max(anchor,index)+1).forEach(x=>selected.add(x.id));
        }else{selected.has(r.id)?selected.delete(r.id):selected.add(r.id);anchor=index;}
        draw();
      };
      draggable(line,[r.id],r.id);list.append(line);
    });
    const end=document.createElement('div');end.className='end';end.textContent='Drop here to move to the end';
    end.ondragover=e=>e.preventDefault();end.ondrop=e=>{e.preventDefault();move(dragIds,null);};list.append(end);
    save.disabled=!dirty;
    status.textContent=dirty
      ? `${selected.size} selected · unsaved order`
      : `${selected.size} selected question(s)`;
  }
  draw();
  return ()=>dragCleanups.forEach(cleanup=>cleanup());
}
"""

_ORDER = st.components.v2.component(
    'templyfier_question_order',
    html='<div class="order-root"></div>',
    js=ORDER_JS,
    css="""
    .order-root {font-family:var(--st-font);color:var(--st-text-color);}
    .toolbar {display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px;}
    button {padding:6px 10px;border:1px solid var(--st-border-color);border-radius:6px;background:var(--st-secondary-background-color);color:inherit;cursor:pointer;}
    button:disabled {opacity:.45;cursor:not-allowed;}
    .save-order:not(:disabled) {background:var(--st-primary-color);color:white;border-color:var(--st-primary-color);}
    .order-list {max-height:420px;overflow:auto;border:1px solid var(--st-border-color);border-radius:8px;}
    .question,.group {display:flex;align-items:center;gap:10px;padding:9px 12px;cursor:grab;border-bottom:1px solid var(--st-border-color);}
    .question span {flex:1;} small {opacity:.7;} input {accent-color:var(--st-primary-color);}
    .group {background:var(--st-secondary-background-color);}
    .selected {outline:1px solid var(--st-primary-color);outline-offset:-1px;}
    .drop-before {border-top:3px solid var(--st-primary-color);}
    .drop-after {border-bottom:3px solid var(--st-primary-color);}
    .end {padding:18px;text-align:center;opacity:.65;}
    .handle {cursor:grab;touch-action:none;border:0;background:transparent;padding:0 3px;font-size:18px;}
    """,
)


def question_order(rows, revision, key):
    return _ORDER(data={'revision': revision, 'rows': [
        {'id':r['Question ID'], 'label':r.get('Metric label') or r['Display label'],
         'group':r.get('Group ID',''), 'groupLabel':r['Display label'], 'type':TEXT.get(r['Type'],r['Type']), 'keep':r['Keep']}
        for r in rows]}, key=key, on_reordered_change=lambda: None)
