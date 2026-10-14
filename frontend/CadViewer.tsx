import React, {useEffect, useRef, useState} from 'react';
import * as THREE from 'three';
import {STLLoader} from 'three/examples/jsm/loaders/STLLoader.js';
import {OBJLoader} from 'three/examples/jsm/loaders/OBJLoader.js';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';

type FileItem = {id:string, name:string, size:number};
type Preview = {status:'ready'|'processing'|'error', url?:string, error?:string};

export default function CadViewer({file, sourceUrl}:{file:FileItem|null; sourceUrl?:string}) {
  const actions = useRef<{reset?:()=>void;wire?:()=>void}>({});
  const [stats,setStats]=useState('');
  const host = useRef<HTMLDivElement>(null);
  const [preview, setPreview] = useState<Preview|null>(null);
  useEffect(() => {
    setPreview(null);
    if (!file) return;
    if (sourceUrl) {setPreview({status:'ready',url:sourceUrl});return}
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const response = await fetch(`/api/files/${file!.id}/preview`);
        if (!response.ok) throw new Error(await response.text());
        const status: Preview = await response.json();
        if (stopped) return;
        setPreview(status);
        if (status.status === 'processing') timer = setTimeout(check, 1500);
      } catch (error) {
        if (!stopped) setPreview({status:'error', error:String(error)});
      }
    }
    check();
    return () => {stopped = true; clearTimeout(timer)};
  }, [file?.id, sourceUrl]);

  useEffect(() => {
    if (!file || preview?.status !== 'ready' || !preview.url || !host.current) return;
    const element = host.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#101b2c');
    const camera = new THREE.PerspectiveCamera(45, element.clientWidth/360, .01, 1e7);
    const renderer = new THREE.WebGLRenderer({antialias:true});
    renderer.setSize(element.clientWidth, 360);
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    scene.add(new THREE.AmbientLight(0xffffff, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2);
    light.position.set(1, 2, 3);
    scene.add(light);
    const axes=new THREE.AxesHelper(1);scene.add(axes);
    let stopped = false;
    let frame = 0;
    fetch(preview.url).then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.arrayBuffer();
    }).then(buffer => {
      if (stopped) return;
      const model = file.name.toLowerCase().endsWith('.obj')
        ? new OBJLoader().parse(new TextDecoder().decode(buffer))
        : new THREE.Mesh(new STLLoader().parse(buffer), new THREE.MeshStandardMaterial({color:0x3db8d3, side:THREE.DoubleSide}));
      scene.add(model);
      let triangles=0;model.traverse(o=>{if(o instanceof THREE.Mesh)triangles+=(o.geometry.index?.count??o.geometry.attributes.position.count)/3});
      const box = new THREE.Box3().setFromObject(model);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length() || 1;
      controls.target.copy(center);
      camera.position.copy(center).add(new THREE.Vector3(size,size,size));
      camera.near = size/10000;
      camera.far = size*100;
      camera.updateProjectionMatrix();
      controls.update();
      axes.position.copy(box.min);axes.scale.setScalar(size/5);
      const dimensions=box.getSize(new THREE.Vector3());
      setStats(`${triangles.toLocaleString()} 三角面 · 尺寸 ${dimensions.toArray().map(v=>v.toFixed(2)).join(' × ')}（源文件单位，请确认）`);
      controls.saveState();actions.current={reset:()=>controls.reset(),wire:()=>model.traverse(o=>{if(o instanceof THREE.Mesh){const materials=Array.isArray(o.material)?o.material:[o.material];materials.forEach(m=>{if('wireframe' in m)(m as THREE.MeshStandardMaterial).wireframe=!(m as THREE.MeshStandardMaterial).wireframe})}})};
    }).catch(error => {if (!stopped) setPreview({status:'error', error:String(error)})});
    const observer=new ResizeObserver(()=>{camera.aspect=element.clientWidth/360;camera.updateProjectionMatrix();renderer.setSize(element.clientWidth,360)});observer.observe(element);
    function draw() {frame = requestAnimationFrame(draw); renderer.render(scene,camera)}
    draw();
    return () => {stopped = true; observer.disconnect();scene.traverse(o=>{if(o instanceof THREE.Mesh){o.geometry.dispose();(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose())}});actions.current={}; cancelAnimationFrame(frame); controls.dispose(); renderer.dispose(); element.removeChild(renderer.domElement)};
  }, [file?.id, preview?.status, preview?.url]);

  return <section className="ff-viewer"><div className="ff-view-tools"><button onClick={()=>actions.current.reset?.()}>适配 / 重置视角</button> <button onClick={()=>actions.current.wire?.()}>实体 / 网格线</button><small>左键旋转 · 滚轮缩放 · 右键平移</small></div><div className="viewer" ref={host}>
    {!file && <span>选择模型查看</span>}
    {file && preview?.status === 'processing' && <span>正在生成 CAD 预览…</span>}
    {file && preview?.status === 'error' && <span>预览失败：{preview.error}</span>}
  </div><small role="status">{stats}</small></section>;
}
