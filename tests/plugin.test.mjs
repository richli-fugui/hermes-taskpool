import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { fileURLToPath } from 'node:url'

const sdk = `
import React, { useSyncExternalStore } from 'react';
const values = {cwd:'C:/Work/A',profile:'default',connectionId:'local',activeSessionId:'s-a',focusedSessionId:'s-a',focusedSessionProfile:'default',gateway:'open'};
window.getValues=()=>values;
const listeners = new Map(Object.keys(values).map(k=>[k,new Set()]));
window.projects = [{id:'a',name:'项目 A',primary_path:'C:/Work/A'},{id:'b',name:'项目 B',primary_path:'C:/Work/B'}];
export const host = {state:Object.fromEntries(Object.keys(values).map(k=>[k,{get:()=>values[k],subscribe:f=>{listeners.get(k).add(f);return()=>listeners.get(k).delete(f)}}])),
 request:async(method,params)=>{if(method==='session.info')return {cwd:window.sessionCwds[params.session_id]};if(window.requestError)throw new Error('offline');return {projects:window.projects}},
 notify:()=>{},composer:{insertText:async(_,text)=>{window.references.push(text);return true}}};
window.setScope = patch => {for(const [k,v] of Object.entries(patch)){if(values[k]===v)continue;values[k]=v;if(k==='cwd')window.sessionCwds[values.focusedSessionId]=v;listeners.get(k)?.forEach(f=>f())}};
window.activateSession = (id,cwd) => {window.sessionCwds[id]=cwd;values.focusedSessionId=id;listeners.get('focusedSessionId').forEach(f=>f())};
export const useValue = a => useSyncExternalStore(a.subscribe,a.get,a.get);
export const Button = ({children,size,variant,...props})=>React.createElement('button',props,children);
export const PALETTE_AREA='palette',ROUTES_AREA='routes',TITLEBAR_AREAS={right:'titleBar.right'};
`
const result = await build({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import plugin from './src/plugin.js';
window.references=[];window.actions=[];window.contributions=[];window.data=new Map();window.failWrites=false;window.serverBoards=new Map();window.sessionCwds={'s-a':'C:/Work/A','s-b':'C:/Work/B'};
window.scope=()=>({connection:window.getValues().connectionId,profile:window.getValues().profile});
window.backendKey=id=>JSON.stringify([window.getValues().connectionId,window.getValues().profile,id]);
window.board=id=>{const k=window.backendKey(id);if(!window.serverBoards.has(k))window.serverBoards.set(k,{project:{id,name:'项目 '+id},revision:0,updatedAt:null,tasks:[]});return window.serverBoards.get(k)};
window.agentWrite=(id,task)=>{const b=window.board(id);b.tasks.unshift(structuredClone(task));b.revision++};
window.pluginRest=async(path,opts={})=>{
  if(window.restError)throw new Error('backend offline')
  const url=new URL(path,'http://local');const segments=url.pathname.split('/').filter(Boolean);const method=opts.method||'GET'
  if(segments.length<3||segments[0]!=='projects')throw new Error('unknown REST path '+path)
  const projectId=segments[1];const board=window.board(projectId);const body=opts.body||{}
  if(segments[2]==='legacy-import'&&method==='POST'){
    board.imported=board.imported||{}
    if(board.imported[body.source_key])return structuredClone(board.imported[body.source_key])
    let inserted=0
    for(const old of body.tasks||[]){if(!board.tasks.some(task=>task.id===old.id)){board.tasks.push(structuredClone(old));inserted++}}
    if(inserted)board.revision++
    const result={inserted,conflicts:0,boardRevision:board.revision};board.imported[body.source_key]=result;return structuredClone(result)
  }
  if(segments[2]!=='tasks')throw new Error('unknown REST path '+path)
  if(method==='GET')return structuredClone(board)
  if(method==='POST'){
    board.requests=board.requests||{}
    if(body.request_key&&board.requests[body.request_key])return structuredClone(board.requests[body.request_key])
    const now=new Date().toISOString();const task={id:'ui-'+Math.random().toString(16).slice(2),title:body.task.title,notes:body.task.notes||'',status:body.task.status||'todo',createdAt:now,updatedAt:now,revision:1}
    board.tasks.unshift(task);board.revision++;const result={task:structuredClone(task),boardRevision:board.revision};if(body.request_key)board.requests[body.request_key]=result;return result
  }
  if(method==='PATCH'){
    const task=board.tasks.find(x=>x.id===segments[3]);if(!task)throw new Error('task not found')
    if(task.revision!==body.expected_revision)throw new Error('任务卡已被修改；未覆盖其他修改')
    Object.assign(task,{...(body.title!==undefined?{title:body.title}:{}),...(body.notes!==undefined?{notes:body.notes}:{}),...(body.status!==undefined?{status:body.status}:{}),updatedAt:new Date().toISOString(),revision:task.revision+1});board.revision++
    return {task:structuredClone(task),boardRevision:board.revision}
  }
  throw new Error('unsupported method')
};
const ctx={storage:{get:(k,f)=>window.data.has(k)?structuredClone(window.data.get(k)):f,set:(k,v)=>{if(!window.failWrites)window.data.set(k,structuredClone(v))}},rest:(path,opts)=>window.pluginRest(path,opts),setInterval:(fn,ms)=>{const id=window.setInterval(fn,Math.min(ms,20));return()=>window.clearInterval(id)},register:c=>window.contributions.push(c),runAction:a=>{window.actions.push(a);return Promise.resolve({ok:true})}};
plugin.register(ctx);let roots=[];
window.mount=()=>{const el=document.createElement('div');el.className='mount';document.body.append(el);const root=createRoot(el);roots.push(root);root.render(window.contributions.find(c=>c.area==='panes').render());return el};
window.unmount=()=>{roots.forEach(r=>r.unmount());roots=[];document.querySelectorAll('.mount').forEach(el=>el.remove())};
window.mount();
const icon=document.createElement('div');icon.id='icon';document.body.append(icon);createRoot(icon).render(window.contributions.find(c=>c.id==='icon').render());`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'js'},bundle:true,write:false,platform:'browser',format:'iife',plugins:[{name:'sdk',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:sdk,loader:'js',resolveDir:fileURLToPath(new URL('..',import.meta.url))}))}}]})
const pause = () => new Promise(r=>setTimeout(r,35))
const key = id => 'board.v1.'+JSON.stringify(['local','default',id])
async function setup(t) {
  const dom = new JSDOM('<body></body>',{url:'http://localhost',runScripts:'dangerously',pretendToBeVisual:true})
  t.after(()=>dom.window.close())
  const w=dom.window;w.structuredClone=structuredClone;w.eval(result.outputFiles[0].text);await pause();await pause()
  const pane=()=>w.document.querySelector('.mount')
  const click=(text,el=pane())=>{const b=[...el.querySelectorAll('button')].find(b=>b.textContent.trim()===text);assert.ok(b,'button '+text);b.click()}
  const input=(selector,value,el=pane())=>{const field=el.querySelector(selector);assert.ok(field,selector);const proto=field.tagName==='TEXTAREA'?w.HTMLTextAreaElement.prototype:field.tagName==='SELECT'?w.HTMLSelectElement.prototype:w.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(field,value);field.dispatchEvent(new w.Event(field.tagName==='SELECT'?'change':'input',{bubbles:true}));}
  const add=async(title,el=pane())=>{input('input',title,el);await pause();click('添加',el);await pause()}
  return {w,pane,click,input,add}
}

test('actual shipping plugin: icon SVG, create/edit/reference/status/reload preserve existing interaction',async t=>{
  const {w,pane,click,input,add}=await setup(t)
  assert.ok(w.document.querySelector('#icon button svg path'))
  w.document.querySelector('#icon button').click();assert.deepEqual([...w.actions],['view.toggleRightSidebar'])
  await add('原型任务');click('原型任务');await pause();input('input','修改任务');input('textarea','说明');input('select','review');await pause();click('保存修改');await pause()
  assert.match(pane().textContent,/修改任务/);assert.match(pane().textContent,/待验收/)
  click('引用 ↗');await pause();assert.match(w.references[0],/修改任务/);assert.match(w.references[0],/不自动执行/)
  w.unmount();w.mount();await pause();await pause();assert.match(pane().textContent,/修改任务/)
})

test('Agent-written shared task becomes visible in an already-open desktop task pool',async t=>{
  const {w,pane}=await setup(t)
  w.agentWrite('a',{id:'agent-1',title:'Agent 写入的任务',notes:'同一份后端数据',status:'blocked',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),revision:1})
  await pause();await pause()
  assert.match(pane().textContent,/Agent 写入的任务/)
})

test('legacy local cards migrate into the shared board without deleting the original copy',async t=>{
  const {w,pane}=await setup(t)
  const legacy={id:'legacy-1',title:'历史本机卡',notes:'保留原始内容',status:'todo',createdAt:'2026-10-01T00:00:00.000Z',updatedAt:'2026-10-02T00:00:00.000Z'}
  const source={version:1,tasks:[legacy],updatedAt:legacy.updatedAt}
  w.data.set(key('a'),source);w.data.delete('migration.v1.'+key('a'));w.unmount();w.mount();await pause();await pause()
  assert.equal(w.board('a').tasks[0].id,'legacy-1')
  assert.deepEqual(JSON.parse(JSON.stringify(w.data.get(key('a')))),source)
  assert.match(pane().textContent,/历史本机卡/)
})

test('corrupt board must never be replaced by a new task',async t=>{
  const {w,pane,add}=await setup(t)
  const corrupt={version:8,tasks:[]};w.data.set(key('a'),corrupt);w.data.delete('migration.v1.'+key('a'));w.unmount();w.mount();await pause();await pause();await add('不能覆盖')
  assert.deepEqual(JSON.parse(JSON.stringify(w.data.get(key('a')))),corrupt)
  assert.match(pane().textContent,/格式异常/)
})

test('backend write failure preserves draft and does not claim the card was saved',async t=>{
  const {w,pane,add}=await setup(t);w.restError=true;await add('尚未保存')
  assert.equal(pane().querySelector('input').value,'尚未保存');assert.match(pane().textContent,/backend offline/)
  assert.doesNotMatch(pane().textContent,/已保存到共享任务池/)
})

test('project switch closes previous editor and cannot write it into another project',async t=>{
  const {w,pane,click,add}=await setup(t);await add('A 私有任务');click('A 私有任务');await pause()
  w.setScope({cwd:'C:/Work/B'});await pause();await pause()
  assert.doesNotMatch(pane().textContent,/任务详情/);assert.doesNotMatch(pane().textContent,/A 私有任务/)
  await add('B 私有任务');assert.equal(w.board('a').tasks[0].title,'A 私有任务');assert.equal(w.board('b').tasks[0].title,'B 私有任务')
})

test('focused chat uses its own project when the global workspace still points elsewhere',async t=>{
  const {w,pane,add}=await setup(t);await add('A 私有任务')
  w.activateSession('s-b','C:/Work/B');await pause();await pause()
  assert.match(pane().textContent,/项目 B/);assert.doesNotMatch(pane().textContent,/A 私有任务/)
  await add('B 私有任务')
  assert.equal(w.board('a').tasks[0].title,'A 私有任务');assert.equal(w.board('b').tasks[0].title,'B 私有任务')
})

test('two mounted surfaces append without overwriting one another',async t=>{
  const {w,pane,add}=await setup(t);const second=w.mount();await pause();await pause()
  await add('第一面板');await add('第二面板',second)
  assert.equal(w.board('a').tasks.length,2)
  assert.match(pane().textContent,/第二面板/)
})

test('same task edited in two surfaces rejects stale save and preserves draft',async t=>{
  const {w,pane,click,input,add}=await setup(t);await add('共同任务');const second=w.mount();await pause();await pause()
  click('共同任务');click('共同任务',second);await pause()
  input('input','第一修改');await pause();click('保存修改');await pause()
  input('input','第二修改',second);await pause();click('保存修改',second);await pause()
  assert.equal(w.board('a').tasks[0].title,'第一修改')
  assert.match(second.textContent,/任务已变化/);assert.equal(second.querySelector('input').value,'第二修改')
})

test('malformed JSON in SDK backing storage is not silently overwritten',async t=>{
  const {w,pane,add}=await setup(t)
  w.localStorage.setItem('hermes.plugin.pp-pane.'+key('a'),'{broken')
  w.data.delete('migration.v1.'+key('a'))
  w.unmount();w.mount();await pause();await pause();await add('不能覆盖坏 JSON')
  assert.equal(w.data.has(key('a')),false);assert.match(pane().textContent,/格式异常/)
})

test('macOS case-sensitive paths do not incorrectly match another project',async t=>{
  const {w,pane}=await setup(t)
  w.projects=[{id:'mac',name:'Mac 项目',primary_path:'/Users/Someone/repo'}]
  w.setScope({cwd:'/Users/Someone/Repo'})
  await pause();await pause()
  assert.match(pane().textContent,/未识别项目/)
})

test('path boundaries and longest folder choose the correct Windows project',async t=>{
  const {w,pane}=await setup(t)
  w.projects=[{id:'parent',name:'父项目',primary_path:'C:/Work'},{id:'child',name:'子项目',primary_path:'C:/Work/App'}]
  w.setScope({cwd:'c:/work/APP/src'});await pause();await pause();assert.match(pane().textContent,/子项目/)
  w.setScope({cwd:'C:/Work/Apple'});await pause();await pause();assert.match(pane().textContent,/父项目/);assert.doesNotMatch(pane().textContent,/子项目/)
})

test('profile/connection switches and failed request never reuse the previous board',async t=>{
  const {w,pane,add}=await setup(t);await add('default 卡片')
  w.requestError=true;w.setScope({profile:'other',focusedSessionProfile:'other',connectionId:'remote'});await pause();await pause()
  assert.match(pane().textContent,/读取项目失败/);assert.doesNotMatch(pane().textContent,/default 卡片/)
  w.requestError=false;w.setScope({gateway:'reconnected'});await pause();await pause();await add('remote 卡片')
  assert.equal(w.serverBoards.get(JSON.stringify(['local','default','a'])).tasks[0].title,'default 卡片')
  assert.equal(w.serverBoards.get(JSON.stringify(['remote','other','a'])).tasks[0].title,'remote 卡片')
})

test('IME confirmation Enter does not prematurely create a task',async t=>{
  const {w,pane,input}=await setup(t);input('input','中文输入');await pause()
  pane().querySelector('input').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true}));await pause()
  assert.equal(w.data.get(key('a'))?.tasks.length||0,0)
})
