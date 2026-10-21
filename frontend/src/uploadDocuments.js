/**
 * Purpose: Choose which PO stays selected after an upload. Uploads are independent; an association
 * records the uploaded pair, not a verified match. (The sidebar no longer uses this; it is kept for its tests.)
 * Input: previousId - the PO selected before; outcome - the PO upload result ({ value } or { error }).
 * Output: the new PO's id when the upload succeeded, otherwise previousId.
 */
export function selectedPOAfterUpload(previousId, outcome) {
  return outcome?.value?.id || previousId;
}

/**
 * Purpose: Upload a Tech Pack and/or a PO. A failure of one does not stop the other; the PO is
 * linked to the Tech Pack only when the Tech Pack upload succeeded. (The sidebar no longer uses
 * this combined upload; it is kept for its tests.)
 * Input: { techPack, po } - the files to upload (either may be missing); clients - { techPack, po }
 * objects with an upload method.
 * Output: a promise of { techPackResult, poResult, warning }, where each result is { value } or { error }.
 */
export async function uploadDocuments({ techPack, po }, clients) {
  const result = { techPackResult: null, poResult: null, warning: '' };
  if (techPack) {
    try { result.techPackResult = { value: await clients.techPack.upload(techPack) }; }
    catch (error) { result.techPackResult = { error: error.message }; }
  }
  if (po) {
    const linkedId = result.techPackResult?.value?.id || null;
    try { result.poResult = { value: await clients.po.upload(po, linkedId) }; }
    catch (error) { result.poResult = { error: error.message }; }
    if (techPack && !linkedId && result.poResult.value) result.warning = 'PO uploaded independently; it is not linked because the Tech Pack upload failed.';
  }
  return result;
}
