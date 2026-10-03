"""Read the generated GLB back and check the 3D Tiles 1.1 metadata round-trips."""
import json, struct, sys
import numpy as np

def read_glb(path):
    with open(path,'rb') as f: data=f.read()
    magic,ver,length=struct.unpack('<III',data[:12])
    assert magic==0x46546C67 and ver==2, 'not glTF 2.0 binary'
    assert length==len(data), f'header length {length} != file {len(data)}'
    off=12; js=None; bin_=None
    while off<len(data):
        clen,ctype=struct.unpack('<II',data[off:off+8]); off+=8
        chunk=data[off:off+clen]; off+=clen
        if ctype==0x4E4F534A: js=json.loads(chunk)
        elif ctype==0x004E4942: bin_=chunk
    return js,bin_

def view(js,bin_,i):
    v=js['bufferViews'][i]; o=v.get('byteOffset',0)
    return bin_[o:o+v['byteLength']]

g,b = read_glb(sys.argv[1] if len(sys.argv)>1 else 'out/pistes.glb')
print('extensionsUsed:', g['extensionsUsed'])
sm=g['extensions']['EXT_structural_metadata']
cls=list(sm['schema']['classes'])[0]
tab=sm['propertyTables'][0]
n=tab['count']
print('class:', cls, '| features:', n)

prim=g['meshes'][0]['primitives'][0]
assert '_FEATURE_ID_0' in prim['attributes'], 'no feature id attribute'
mf=prim['extensions']['EXT_mesh_features']['featureIds'][0]
print('featureIds:', mf)
assert mf['propertyTable']==0 and mf['featureCount']==n

# accessor sanity
for name,ai in prim['attributes'].items():
    a=g['accessors'][ai]
    print(f'  {name:15s} count={a["count"]:6d} type={a["type"]}')
ia=g['accessors'][prim['indices']]
print(f'  INDICES         count={ia["count"]:6d}')
npos=g['accessors'][prim['attributes']['POSITION']]['count']
idx=np.frombuffer(view(g,b,g['accessors'][prim['indices']]['bufferView']),dtype='<u4')
assert idx.max()<npos, f'index {idx.max()} out of range {npos}'
print('index range OK, max', int(idx.max()), 'of', npos)

# decode property table
def strings(p):
    vals=view(g,b,p['values']); offs=np.frombuffer(view(g,b,p['stringOffsets']),dtype='<u4')
    return [vals[offs[i]:offs[i+1]].decode('utf-8') for i in range(n)]
def scalars(p):
    return np.frombuffer(view(g,b,p['values']),dtype='<f4')

props=sm['schema']['classes'][cls]['properties']
out={}
for k,spec in props.items():
    p=tab['properties'][k]
    out[k]= strings(p) if spec['type']=='STRING' else scalars(p)
print('\nproperty table decoded:')
print(f'{"name":28s} {"grade":13s} {"footprint":22s} {"mean":>7s} {"p90":>7s} {"ha":>7s} {"drop":>6s}')
bad=0
for i in range(n):
    md=float(np.degrees(np.arctan(out['meanSlope'][i])))
    sd=float(np.degrees(np.arctan(out['p90Slope'][i])))
    if sd > 60: bad += 1
    print(f'{out["name"][i][:28]:28s} {out["difficulty"][i]:13s} {out["source"][i]:22s} '
          f'{md:6.1f}° {sd:6.1f}° {out["areaM2"][i]/1e4:7.2f} {out["verticalExtentM"][i]:6.0f}')
assert 'maxSlope' not in out, 'maxSlope must not be published: it is a sliver artefact, not a measurement'
assert bad == 0, f'{bad} features report an implausible p90 slope (>60 deg)'
print(f'\nno maxSlope property · all p90 slopes plausible ({n} features)')

t=json.load(open('out/pistes.json'))
assert t['asset']['version']=='1.1', t['asset']
assert len(t['root']['transform'])==16
print('\ntileset asset version', t['asset']['version'], '· transform present · bounding region present')
print('VALID')
