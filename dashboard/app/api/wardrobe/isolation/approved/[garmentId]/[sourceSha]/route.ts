import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { NextResponse } from 'next/server';
import { AGENT_DATA_ROOT } from '@/lib/data-root';
import { findActiveGarment, garmentSourceImage } from '@/lib/wardrobe-registry';

const BASE = path.join(AGENT_DATA_ROOT,'projects','dressup-simulator','isolation_candidates');
const ID = /^(?!\.{1,2}$)[A-Za-z0-9._-]{1,160}$/;
const SHA = /^[a-f0-9]{64}$/;
const digest=(bytes:Buffer)=>crypto.createHash('sha256').update(bytes).digest('hex');

// Only a reviewed, canonical approved garment may be served to the try-on worker.
// This URL contains no filesystem paths and never reveals unapproved candidate files.
export async function GET(_request: Request, context:{
  params:Promise<{garmentId:string;sourceSha:string}>
}) {
  const {garmentId,sourceSha}=await context.params;
  if(!ID.test(garmentId)||!SHA.test(sourceSha)){
    return NextResponse.json({error:'Invalid asset selector'},{status:400});
  }
  const garment=findActiveGarment(garmentId);
  const approved=garment?.tryOnSource;
  const image=garment?garmentSourceImage(garment):null;
  const fingerprint=image?crypto.createHash('sha256').update(image).digest('hex'):'';
  if(approved?.schema!=='agentos.wardrobe-isolated-product/v1' ||
     approved.state!=='approved' || !approved.approvedFingerprint ||
     approved.approvedFingerprint!==fingerprint ||
     !approved.productIR || !Array.isArray(approved.productIR.mustKeep) ||
     !approved.approvedAssetSha256 || !SHA.test(approved.approvedAssetSha256) ||
     !approved.isolatedImageUrl ||
     !/^https:\/\//.test(approved.isolatedImageUrl) ||
     !approved.isolatedImageUrl.endsWith('/'+garmentId+'/'+sourceSha)){
    return NextResponse.json({error:'Approved garment not found'},{status:404,headers:{'Cache-Control':'no-store'}});
  }
  try {
    const folder=path.join(BASE,garmentId,sourceSha);
    const receiptFile=path.join(folder,'candidate-receipt.json');
    const stat=fs.lstatSync(receiptFile);
    if(!stat.isFile()||stat.isSymbolicLink()||stat.size>200_000)throw Error('invalid receipt');
    const receipt=JSON.parse(fs.readFileSync(receiptFile,'utf8'));
    if(receipt.garmentId!==garmentId ||receipt.sourceAssetSha256!==sourceSha ||
       receipt.approved!==true||receipt.review?.state!=='accepted' ||
       receipt.isolatedAssetSha256!==approved.approvedAssetSha256 ||
       receipt.productIR?.schema!=='agentos.wardrobe-product-ir/v1' ||
       receipt.productIR?.category!==approved.productIR.category){
      throw Error('not accepted');
    }
    const file=path.join(folder,'garment.png');
    const assetStat=fs.lstatSync(file);
    if(!assetStat.isFile()||assetStat.isSymbolicLink()||assetStat.size>15_000_000)throw Error('invalid PNG');
    const data=fs.readFileSync(file);
    if(digest(data)!==receipt.isolatedAssetSha256 ||
       !data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw Error('invalid candidate hash');
    return new NextResponse(new Uint8Array(data), {headers:{
      'Content-Type':'image/png','Cache-Control':'public,max-age=300',
      'X-Content-Type-Options':'nosniff',
    }});
  } catch {
    return NextResponse.json({error:'Approved asset unavailable'},{status:404,headers:{'Cache-Control':'no-store'}});
  }
}
