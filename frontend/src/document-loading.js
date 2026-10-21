import { api } from './api.js';

export async function loadSelectedDocument(id, currentId, commit, fetchDocument = api.get) {
  const row = await fetchDocument(id);
  if (currentId() === id) commit(row);
  return row;
}
