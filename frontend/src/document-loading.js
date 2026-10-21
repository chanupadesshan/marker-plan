import { api } from './api.js';

/**
 * Purpose: Fetch a Tech Pack and hand it to the screen only if the user is still looking at it,
 * so a slow answer cannot replace a document selected afterwards.
 * Input: id - the Tech Pack to load; currentId - a function returning the currently selected id;
 * commit - a function that stores the loaded row; fetchDocument - the loader (defaults to api.get).
 * Output: a promise of the loaded row (it is returned even when it was not committed).
 */
export async function loadSelectedDocument(id, currentId, commit, fetchDocument = api.get) {
  const row = await fetchDocument(id);
  if (currentId() === id) commit(row);
  return row;
}
