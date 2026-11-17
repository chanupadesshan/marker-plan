import React from 'react';
import { Check, FileUp, ScanText } from 'lucide-react';

export default function TechPackProgress({ current, uploading = false, kind = 'techpack' }) {
  if (!uploading && !['queued', 'processing'].includes(current?.status)) return null;
  const progress = current?.progress;
  const stage = uploading ? 'uploading' : progress?.stage || (current?.status === 'queued' ? 'queued' : 'locating');
  const isPO = kind === 'po';
  const name = isPO ? 'Purchase Order' : 'Tech Pack';
  const titles = { uploading: `Uploading ${name}`, queued: `Your ${name} is in the queue`, locating: isPO ? 'Preparing purchase-order pages' : 'Finding material pages', extracting: isPO ? 'Reading purchase-order pages' : 'Reading your Wovens and Knits BOM', finalizing: 'Preparing your results' };
  const percent = !uploading && Number.isFinite(progress?.percent) ? Math.max(0, Math.min(100, progress.percent)) : null;
  const detail = progress?.total_pages ? `${progress.completed_pages} of ${progress.total_pages} ${isPO ? 'PO' : 'material'} pages read` : stage === 'uploading' ? 'Sending your PDF. Extraction starts after upload.' : stage === 'queued' ? 'Waiting to start. This view updates automatically.' : isPO ? 'Preparing the PDF for extraction. This view updates automatically.' : 'Checking the PDF for BOM tables. This view updates automatically.';
  const activeStep = stage === 'uploading' ? 0 : ['queued', 'locating'].includes(stage) ? 1 : stage === 'extracting' ? 2 : 3;
  const steps = ['Upload PDF', isPO ? 'Prepare pages' : 'Find BOM pages', isPO ? 'Read PO pages' : 'Read materials', 'Prepare results'];
  const Icon = uploading ? FileUp : ScanText;
  return <section className="techpack-progress panel" aria-label={`${name} extraction progress`}>
    <div className="techpack-progress-heading"><span className="techpack-progress-icon"><Icon size={22}/></span>
      <div><h2>{titles[stage] || titles.locating}</h2><p role="status">{detail}</p></div>
      {percent !== null && <span className="techpack-progress-percent">{percent}%<small>pages read</small></span>}
    </div>
    <div className={`techpack-progress-track ${percent === null ? 'indeterminate' : ''}`} role="progressbar" aria-label={`${name} extraction`}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined} aria-valuetext={detail}>
      <span style={percent === null ? undefined : { width: `${percent}%` }}/>
    </div>
    <ol className="techpack-progress-steps">{steps.map((label, index) => <li key={label} className={index < activeStep ? 'done' : index === activeStep ? 'active' : ''} aria-current={index === activeStep ? 'step' : undefined}>
      <span>{index < activeStep ? <Check size={12}/> : index + 1}</span>{label}
    </li>)}</ol>
  </section>;
}
