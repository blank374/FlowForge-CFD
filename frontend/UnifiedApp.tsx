import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import CadViewer from './CadViewer';
import './style.css';

type Project = {id:string; name:string};
type FileItem = {id:string; name:string; size:number};
type Stage = {name:string; status:string; evidence?:string|null};
type Version = {version:number; filename:string; status:string; report:any; download_url:string; review_project_url:string; review_project_available:boolean; manual_edit?:{path:string;changed:boolean}};
type Job = {id:string; project_id:string; profile:string; status:string; stage:string; version:number; created:string; error:string|null; stages?:Stage[]; versions?:Version[]; run?:any; result?:any; artifacts?:string[]};
type Inspection = {status:string; kind:string; signature:string; sha256:string; volume_mesh_verified:boolean};

async function api<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch('/api'+path,init);
  if(!response.ok){const raw=await response.text();let message=raw;try{message=JSON.parse(raw).detail||raw}catch{}throw new Error(message)}
  return response.json();
}
const statusText:Record<string,string>={PASSED:'已通过',RUNNING:'运行中',PENDING:'待执行',BLOCKED:'已阻断',NEEDS_MANUAL_REPAIR:'待人工处理',WAITING_FOR_REVIEW:'待审核',PAUSED:'已暂停',FAILED:'失败',CANCELLED:'已取消'};
function formatSize(bytes:number){return bytes>=1048576?(bytes/1048576).toFixed(1)+' MB':Math.max(1,Math.round(bytes/1024))+' KB'}
function shortDate(value:string){return new Date(value).toLocaleString('zh-CN',{hour12:false})}

function App(){
  const [projects,setProjects]=useState<Project[]>([]),[project,setProject]=useState<Project|null>(null),[projectName,setProjectName]=useState('');
  const [files,setFiles]=useState<FileItem[]>([]),[file,setFile]=useState<FileItem|null>(null),[inspection,setInspection]=useState<Inspection|null>(null);
  const [jobs,setJobs]=useState<Job[]>([]),[job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[log,setLog]=useState('');

  async function loadProjects(){setProjects(await api<Project[]>('/projects'))}
  async function loadProject(p:Project){const [f,j]=await Promise.all([api<FileItem[]>('/projects/'+p.id+'/files'),api<Job[]>('/workflows/projects/'+p.id)]);setFiles(f);setJobs(j)}
  async function loadJob(id:string){setJob(await api<Job>('/workflows/'+id))}
  useEffect(()=>{loadProjects().catch(e=>setError(String(e)))},[]);
  useEffect(()=>{if(!project)return;loadProject(project).catch(e=>setError(String(e)));const timer=setInterval(()=>loadProject(project).catch(()=>{}),3000);return()=>clearInterval(timer)},[project?.id]);
  useEffect(()=>{if(!job)return;const timer=setInterval(()=>loadJob(job.id).catch(()=>{}),2500);return()=>clearInterval(timer)},[job?.id]);

  async function createProject(){if(!projectName.trim())return;setBusy(true);try{const value=await api<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:projectName.trim()})});setProjectName('');await loadProjects();setProject(value)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function uploadFile(input:File){if(!project)return;const form=new FormData();form.append('file',input);setBusy(true);try{await api('/projects/'+project.id+'/files',{method:'POST',body:form});await loadProject(project)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function selectFile(value:FileItem){setFile(value);setInspection(null);try{setInspection(await api<Inspection>('/files/'+value.id+'/inspect'))}catch(e){setError(String(e))}}
  async function start(profile:'l1_full'|'general',manual=false){if(!project||!file)return;setBusy(true);try{const created=await api<Job>('/workflows/projects/'+project.id+'?file_id='+encodeURIComponent(file.id)+'&profile='+profile+'&manual='+manual,{method:'POST'});setJob(created);setLog('');await loadProject(project)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function repair(input:File){if(!job)return;const form=new FormData();form.append('file',input);setBusy(true);try{setJob(await api<Job>('/workflows/'+job.id+'/repair',{method:'POST',body:form}));setLog('');if(project)await loadProject(project)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function openManual(){if(!job)return;setBusy(true);try{const opened=await api<{status:string;path:string;job:Job}>('/workflows/'+job.id+'/open-in-ansa',{method:'POST'});setJob(opened.job);setError('');if(project)await loadProject(project)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function submitLocal(){if(!job)return;setBusy(true);try{setJob(await api<Job>('/workflows/'+job.id+'/submit-local-repair',{method:'POST'}));setError('');if(project)await loadProject(project)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function manual(){if(!job)return;try{setJob(await api<Job>('/workflows/'+job.id+'/manual',{method:'POST'}))}catch(e){setError(String(e))}}
  async function approve(){if(!job)return;const reviewer=window.prompt('审核人姓名');if(!reviewer?.trim())return;try{setJob(await api<Job>('/workflows/'+job.id+'/approve?reviewer='+encodeURIComponent(reviewer.trim()),{method:'POST'}))}catch(e){setError(String(e))}}
  async function cancel(){if(!job?.run)return;try{await api('/runs/'+job.run.id+'/cancel',{method:'POST'});await loadJob(job.id)}catch(e){setError(String(e))}}
  const latest=job?.versions?.[job.versions.length-1];
  const cad=!!file&&/\.(igs|iges|stp|step|ansa)$/i.test(file.name);
  const iges=!!file&&/\.(igs|iges)$/i.test(file.name);
  return <div className="ff-shell"><header className="ff-header"><div><h1>FlowForge CFD</h1><span>从模型到报告 · 自动执行，人工可接管</span></div><span className="ff-local">本机工程工作台</span></header>
    {error&&<div className="ff-error">{error}<button onClick={()=>setError('')}>关闭</button></div>}
    <div className="ff-layout"><aside className="ff-sidebar"><h2>工程</h2><div className="ff-create"><input value={projectName} onChange={e=>setProjectName(e.target.value)} onKeyDown={e=>e.key==='Enter'&&createProject()} placeholder="新工程名称"/><button disabled={busy} onClick={createProject}>新建</button></div>{projects.map(p=><button key={p.id} className={'ff-project '+(project?.id===p.id?'selected':'')} onClick={()=>{setProject(p);setFile(null);setInspection(null);setJob(null);setLog('')}}>{p.name}</button>)}</aside>
      <main className="ff-main">{project?<><div className="ff-title"><div><small>当前工程</small><h2>{project.name}</h2></div><span>{jobs.length} 个任务</span></div>
        <section className="ff-card"><div className="ff-card-head"><div><h3>1　选择文件</h3><p>原文件会保留，处理在独立任务目录进行。</p></div><label className="ff-upload">上传文件<input type="file" accept=".igs,.iges,.step,.stp,.ansa,.stl,.obj" onChange={e=>e.target.files?.[0]&&uploadFile(e.target.files[0])}/></label></div><div className="ff-files">{files.map(item=><button key={item.id} className={'ff-file '+(file?.id===item.id?'selected':'')} onClick={()=>selectFile(item)}><strong>{item.name}</strong><small>{formatSize(item.size)}</small></button>)}{!files.length&&<p className="ff-muted">上传 IGS、STEP 或 ANSA 工程开始。</p>}</div>{file&&<><div className="ff-file-meta"><a href={'/api/files/'+file.id}>下载原文件</a>{inspection&&<span>识别：{inspection.kind} / {inspection.signature} · {inspection.status}</span>}</div>{inspection&&<small className="ff-hash">SHA-256：{inspection.sha256}</small>}{/\.(ansa|pw|cgns)$/i.test(file.name)?<p className="ff-muted">工程文件请在原生软件中查看。</p>:<CadViewer file={file}/>}</>}</section>
        <section className="ff-card"><h3>2　启动流程</h3><div className="ff-start-grid"><div><strong>已验证完整流程</strong><p>20 mm L1 球体：ANSA → Pointwise → OpenFOAM → ParaView → 报告。其他外形会被几何门槛拦截。</p><button disabled={!iges||busy} onClick={()=>start('l1_full')}>从导入运行到报告</button></div><div><strong>复杂模型与人工接管</strong><p>ANSA 只做导入和检查。遇到问题，在 ANSA GUI 中处理后回传复检。</p><button disabled={!cad||busy} onClick={()=>start('general')}>自动检查</button> <button className="ff-secondary" disabled={!cad||busy} onClick={()=>start('general',true)}>直接人工处理</button></div></div></section>
        <section className="ff-card"><div className="ff-card-head"><div><h3>3　任务进度与结果</h3><p>每个阶段以真实日志和文件为准。</p></div></div><div className="ff-task-grid"><div className="ff-task-list">{jobs.map(item=><button className={'ff-task '+(job?.id===item.id?'selected':'')} key={item.id} onClick={()=>{loadJob(item.id).catch(e=>setError(String(e)));setLog('')}}><strong>{item.profile==='l1_full'?'完整 CFD 流程':'ANSA 人工协作流程'}</strong><small>{shortDate(item.created)} · {statusText[item.status]||item.status} · v{item.version}</small></button>)}{!jobs.length&&<p className="ff-muted">暂无任务。</p>}</div><div className="ff-detail">{job?<><div className="ff-detail-head"><strong>{job.profile==='l1_full'?'完整 CFD 流程':'ANSA 几何任务'}</strong><span className={'ff-badge '+job.status.toLowerCase()}>{statusText[job.status]||job.status}</span></div><div className="ff-stage-list">{job.stages?.map((stage,index)=><div className={'ff-stage '+stage.status.toLowerCase()} key={index}><b>{index+1}</b><div><strong>{stage.name}</strong><small>{statusText[stage.status]||stage.status}</small></div>{stage.evidence&&job.run&&<a href={'/api/runs/'+job.run.id+'/artifacts/'+stage.evidence}>证据</a>}</div>)}</div>{job.error&&<p className="ff-error-inline">{job.error}</p>}
          {job.profile==='l1_full'&&job.run&&<>{['running','cancelling'].includes(job.run.status)&&<button className="ff-secondary" onClick={cancel}>取消运行</button>}{job.result&&<details><summary>计算结果与网格数据</summary><pre>{JSON.stringify(job.result,null,2)}</pre></details>}{job.run.artifacts?.filter((name:string)=>['U.png','p.png','residuals.png'].includes(name)).map((name:string)=><img className="ff-result" alt={name} key={name} src={'/api/runs/'+job.run.id+'/preview/'+name}/>)}<div className="ff-artifacts">{job.run.artifacts?.filter((name:string)=>['report.md','openfoam_case.zip','run_summary.json','solver.log','paraview.log'].includes(name)).map((name:string)=><a key={name} href={'/api/runs/'+job.run.id+'/artifacts/'+name}>{name}</a>)}</div><details><summary>运行日志</summary><pre>{job.run.log||'等待日志…'}</pre></details></>}
          {latest&&<div className="ff-handoff"><h4>当前版本 · v{latest.version}</h4><p>{latest.filename}</p><div className="ff-artifacts">{['NEEDS_MANUAL_REPAIR','WAITING_FOR_REVIEW','PAUSED'].includes(job.status)||job.profile==='general'&&job.status==='PASSED'?<button disabled={busy} onClick={openManual}>在本机 ANSA 打开工作副本</button>:null}<a href={latest.download_url}>下载输入文件</a>{latest.review_project_available&&<a href={latest.review_project_url}>下载 ANSA 检查工程</a>}</div>{latest.manual_edit&&<div className="ff-local-edit"><p>ANSA 工作副本：<code>{latest.manual_edit.path}</code></p><p>在 ANSA 中保存到此路径，然后提交复检。原文件和旧版本不会被覆盖。{job.profile==='l1_full'&&'完整流程仍只接受 IGES，请将修复结果导出为这里的 .igs/.iges 文件。'}</p><button disabled={busy||!latest.manual_edit.changed||job.status!=='NEEDS_MANUAL_REPAIR'} onClick={submitLocal}>提交本机修复并复检</button>{!latest.manual_edit.changed&&<small>等待保存后的文件变化</small>}</div>}{latest.report&&<details><summary>ANSA 检查报告</summary><pre>{JSON.stringify(latest.report,null,2)}</pre></details>}</div>}
          {job.profile==='general'&&latest&&<><button className="ff-secondary" onClick={()=>api<{log:string}>('/workflows/'+job.id+'/versions/'+latest.version+'/log').then(x=>setLog(x.log)).catch(e=>setError(String(e)))}>查看 ANSA 日志</button>{log&&<pre>{log}</pre>}{['WAITING_FOR_REVIEW','PASSED'].includes(job.status)&&<button className="ff-secondary" onClick={manual}>转人工处理</button>}{job.status==='WAITING_FOR_REVIEW'&&<button onClick={approve}>确认几何检查</button>}</>}
          {job.status==='NEEDS_MANUAL_REPAIR'&&<div className="ff-repair"><strong>人工处理后继续</strong><p>推荐点击上方按钮在 ANSA 打开工作副本，保存后直接提交复检。若使用别的电脑或另存到其他位置，也可选择修复文件上传。{job.profile==='l1_full'&&'完整流程仅接受修复后的 IGES 球体。'}</p><label className="ff-upload">选择修复文件上传<input type="file" accept={job.profile==='l1_full'?'.igs,.iges':'.ansa,.igs,.iges,.step,.stp'} onChange={e=>e.target.files?.[0]&&repair(e.target.files[0])}/></label></div>}
          {job.profile==='general'&&job.status==='PASSED'&&<p className="ff-warning">几何已审核。通用 Pointwise 与求解模板尚未验证，后续阶段保持阻断。</p>}</>:<p className="ff-muted">选择左侧任务查看进度、问题和产物。</p>}</div></div></section>
      </>:<div className="ff-empty"><h2>开始一个 CFD 工程</h2><p>在左侧新建或选择工程，再上传模型。</p></div>}</main></div>
  </div>
}

createRoot(document.getElementById('root')!).render(<App/>);
