// Uploads are independent. Association records the uploaded pair, not a verified match.
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
