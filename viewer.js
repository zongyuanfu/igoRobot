import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {GLTFLoader} from './vendor/loaders/GLTFLoader.js';

const unit = new THREE.Vector3(1,1,1);
const transform = (xyz, xyzw) => new THREE.Matrix4().compose(new THREE.Vector3(...xyz), new THREE.Quaternion(...xyzw), unit);

export class TrajectoryViewer {
  constructor(host) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({antialias:true, alpha:false, preserveDrawingBuffer:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.setClearColor(0xf1f3f3);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.domElement.tabIndex=0;
    this.renderer.domElement.setAttribute('aria-label','3D robot view. Arrow keys orbit; plus and minus zoom.');
    host.append(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(37,1,.01,100);
    this.camera.up.set(0,0,1);
    this.controls = new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping=false;
    this.controls.minDistance=.5; this.controls.maxDistance=8;
    this.controls.maxPolarAngle=Math.PI*.92;
    this.controls.addEventListener('change',()=>this.render());
    this.scene.add(new THREE.HemisphereLight(0xffffff,0x73818d,1.8));
    const light=new THREE.DirectionalLight(0xffffff,2.3); light.position.set(2,-3,5); this.scene.add(light);
    const fill=new THREE.DirectionalLight(0xd6e5ef,1.1); fill.position.set(-3,1,2); this.scene.add(fill);
    this.world=new THREE.Group(); this.scene.add(this.world);
    this.arm=new THREE.Group(); this.scene.add(this.arm);
    this.spheres=new THREE.Group(); this.spheres.visible=false; this.scene.add(this.spheres);
    this.links=[]; this.sphereMeshes=[];
    this.resize=new ResizeObserver(()=>{const {width,height}=host.getBoundingClientRect(); this.renderer.setSize(width,height);this.camera.aspect=width/height;this.camera.updateProjectionMatrix();this.reset();this.render();});
    this.resize.observe(host);
    this.renderer.domElement.addEventListener('keydown',e=>{
      const offsets={ArrowLeft:[-.12,0],ArrowRight:[.12,0],ArrowUp:[0,-.1],ArrowDown:[0,.1]};
      if(offsets[e.key]){e.preventDefault();const spherical=new THREE.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target).applyQuaternion(new THREE.Quaternion().setFromUnitVectors(this.camera.up,new THREE.Vector3(0,1,0))));spherical.theta+=offsets[e.key][0];spherical.phi+=offsets[e.key][1];spherical.makeSafe();const v=new THREE.Vector3().setFromSpherical(spherical).applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),this.camera.up));this.camera.position.copy(this.controls.target).add(v);this.controls.update();}
      if(['+','=','-'].includes(e.key)){e.preventDefault();this.camera.position.sub(this.controls.target).multiplyScalar(e.key==='-'?1.1:.9).add(this.controls.target);this.controls.update();}
    });
    this.renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();host.dispatchEvent(new CustomEvent('viewer-failed'));});
  }
  async init() {
    const response=await fetch(new URL('./data/robot.json',import.meta.url));
    if(!response.ok) throw Error('Robot data could not be loaded.');
    this.model=await response.json();
    const fk=this.model.fk;
    this.base=transform(fk.base_xyz,fk.base_quat);
    this.origins=fk.joint_origins_xyz.map((v,i)=>transform(v,fk.joint_origins_quat[i]));
    this.hand=transform(fk.ee_xyz,fk.ee_quat);
    this.fingers=fk.finger_xyz.map((xyz,i)=>transform(xyz,fk.finger_quat[i]));
    const loader=new GLTFLoader();
    const names=[...Array.from({length:8},(_,i)=>`link${i}`),'hand','finger'];
    const models=await Promise.all(names.map(n=>loader.loadAsync(new URL(`./assets/${n}.glb`,import.meta.url).href)));
    models.slice(0,9).forEach(({scene},i)=>{
      const group=new THREE.Group();group.matrixAutoUpdate=false;group.add(scene);this.links.push(group);this.arm.add(group);
      scene.traverse(node=>{if(node.isMesh){node.material=new THREE.MeshStandardMaterial({color:node.material?.color || 0xe5e7e8,vertexColors:!!node.geometry.getAttribute('color'),metalness:.12,roughness:.47});}});
    });
    this.fingers.forEach(()=>{
      const group=new THREE.Group();group.matrixAutoUpdate=false;
      group.add(models[9].scene.clone(true));this.links.push(group);this.arm.add(group);
    });
    const geometry=new THREE.SphereGeometry(1,16,10);
    const material=new THREE.MeshBasicMaterial({color:0x3792b3,transparent:true,opacity:.16,depthWrite:false,wireframe:true});
    this.model.radii.forEach(r=>{const sphere=new THREE.Mesh(geometry,material);sphere.scale.setScalar(r);this.sphereMeshes.push(sphere);this.spheres.add(sphere);});
  }
  clearWorld() {
    this.world.traverse(node=>{node.geometry?.dispose();if(node.material){for(const m of Array.isArray(node.material)?node.material:[node.material])m.dispose();}});
    this.world.clear();
  }
  load(data) {
    if(data.model_fingerprint!==this.model.fingerprint) throw Error("Trajectory and robot model versions differ. Reload the page.");
    this.data=data; this.clearWorld();
    const bounds=new THREE.Box3(new THREE.Vector3(-.25,-.45,-.25),new THREE.Vector3(.7,.45,.85));
    for(const [kind,items] of Object.entries(data.scene)) for(const [name,item] of Object.entries(items)){
      let geometry;
      if(kind==='cuboid')geometry=new THREE.BoxGeometry(...item.dims);
      else if(kind==='sphere')geometry=new THREE.SphereGeometry(item.radius,28,18);
      else if(kind==='cylinder'){geometry=new THREE.CylinderGeometry(item.radius,item.radius,item.height,28);geometry.rotateX(Math.PI/2);}
      else if(kind==='capsule'){geometry=new THREE.CapsuleGeometry(item.radius,item.height,6,20);geometry.rotateX(Math.PI/2);}
      else throw Error(`Unsupported obstacle: ${kind}`);
      const material=new THREE.MeshStandardMaterial({color:kind==='cuboid'?0x9faab2:0xaab2b9,roughness:.85,metalness:.02,transparent:true,opacity:.6,depthWrite:false,side:THREE.DoubleSide});
      const mesh=new THREE.Mesh(geometry,material);
      const p=item.pose;mesh.position.set(...p.slice(0,3));mesh.quaternion.set(p[4],p[5],p[6],p[3]);mesh.name=name;
      const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geometry,25),new THREE.LineBasicMaterial({color:0x7b8a94,transparent:true,opacity:.43}));mesh.add(edges);
      this.world.add(mesh);mesh.updateMatrixWorld();bounds.expandByObject(mesh);
    }
    const points=data.ee.map(p=>new THREE.Vector3(...p));
    this.path=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:0x287b9e}));
    this.world.add(this.path);
    for(const p of points)bounds.expandByPoint(p);
    const marker=new THREE.Mesh(new THREE.SphereGeometry(.022,20,12),new THREE.MeshStandardMaterial({color:0xbf8544,roughness:.5}));
    marker.position.set(...data.goal.slice(0,3));this.world.add(marker);
    const axis=new THREE.AxesHelper(.105);axis.position.copy(marker.position);axis.quaternion.set(...data.goal.slice(3));this.world.add(axis);
    const grid=new THREE.GridHelper(3.4,34,0xbec9ce,0xdce2e4);grid.rotation.x=Math.PI/2;
    grid.position.set(.2,0,Math.min(-.14,bounds.min.z-.055));grid.material.transparent=true;grid.material.opacity=.65;this.world.add(grid);
    this.target=bounds.getCenter(new THREE.Vector3());
    this.bounds=bounds;
    this.reset();this.setTime(0);
  }
  reset() {
    if(!this.target)return;
    this.controls.target.copy(this.target);
    // View from the open, negative-x side; positive z remains vertical.
    const direction=new THREE.Vector3(-1.65,-2.4,1.35).normalize();
    const right=new THREE.Vector3().crossVectors(this.camera.up,direction).normalize();
    const up=new THREE.Vector3().crossVectors(direction,right).normalize();
    const tanV=Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2)),tanH=tanV*this.camera.aspect;
    let distance=2;
    for(const x of [this.bounds.min.x,this.bounds.max.x])for(const y of [this.bounds.min.y,this.bounds.max.y])for(const z of [this.bounds.min.z,this.bounds.max.z]){
      const point=new THREE.Vector3(x,y,z).sub(this.target);
      distance=Math.max(distance,point.dot(direction)+Math.max(Math.abs(point.dot(up))/tanV,Math.abs(point.dot(right))/tanH));
    }
    this.camera.position.copy(this.target).add(direction.multiplyScalar(distance*1.08));
    this.controls.update();this.render();
  }
  setTime(time) {
    if(!this.data)return;
    const {times,joints}=this.data;
    let lo=0,hi=times.length-1;
    while(hi-lo>1){const mid=(lo+hi)>>1;if(times[mid]>time)hi=mid;else lo=mid;}
    const alpha=THREE.MathUtils.clamp((time-times[lo])/(times[hi]-times[lo]),0,1);
    const q=joints[lo].map((v,i)=>v+(joints[hi][i]-v)*alpha);
    const matrices=[this.base.clone()];
    q.forEach((angle,i)=>matrices.push(matrices[i].clone().multiply(this.origins[i]).multiply(new THREE.Matrix4().makeRotationZ(angle))));
    matrices.push(matrices[7].clone().multiply(this.hand));
    this.fingers.forEach(finger=>matrices.push(matrices[8].clone().multiply(finger)));
    this.links.forEach((link,i)=>{link.matrix.copy(matrices[i]);link.matrixWorldNeedsUpdate=true;});
    this.sphereMeshes.forEach((mesh,i)=>mesh.position.fromArray(this.model.centers[i]).applyMatrix4(matrices[this.model.links[i]]));
    this.currentMatrices=matrices;
    this.render();
  }
  setLayers(path,spheres){if(this.path)this.path.visible=path;this.spheres.visible=spheres;this.render();}
  render(){this.renderer.render(this.scene,this.camera);}
}
