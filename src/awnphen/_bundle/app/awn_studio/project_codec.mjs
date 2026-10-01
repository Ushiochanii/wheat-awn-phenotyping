import {validateProject} from './core.mjs?v=20260927-07';
import {PROJECT_SCHEMA} from './contracts.mjs?v=20260927-07';

export const PROJECT_STORAGE_SCHEMA = 'awn-studio-project-v2';

export function encodeProject(project) {
  const runtime = validateProject(project);
  return {
    schema: PROJECT_STORAGE_SCHEMA,
    updatedAt: runtime.updatedAt ?? null,
    pages: runtime.pages.map(page => {
      if (!page.sourcePageId) return {...page};
      const {src: _sourceImage, ...stored} = page;
      return stored;
    })
  };
}

export function decodeProject(stored) {
  if (!stored || typeof stored !== 'object') {
    throw new Error('Not a valid Awn Studio project file.');
  }

  if (stored.schema === PROJECT_SCHEMA) {
    return validateProject(stored);
  }

  if (stored.schema !== PROJECT_STORAGE_SCHEMA || !Array.isArray(stored.pages)) {
    throw new Error('Not a valid Awn Studio project file.');
  }

  const rawPages = stored.pages;
  const roots = new Map(
    rawPages
      .filter(page => !page.sourcePageId)
      .map(page => [String(page.id), page])
  );

  const pages = rawPages.map(page => {
    if (!page.sourcePageId) return page;
    const source = roots.get(String(page.sourcePageId));
    if (!source || (!source.src && !source.assetRef)) {
      throw new Error(
        `Measurement result ${page.id ?? '(unknown)'} references a missing source image.`
      );
    }
    if (page.width !== source.width || page.height !== source.height) {
      throw new Error(
        `Measurement result ${page.id ?? '(unknown)'} does not match its source image dimensions.`
      );
    }
    return {
      ...page,
      ...(source.src ? {src: source.src} : {}),
      ...(source.assetRef ? {assetRef: source.assetRef} : {})
    };
  });

  return validateProject({
    schema: PROJECT_SCHEMA,
    updatedAt: stored.updatedAt ?? undefined,
    pages
  });
}

export function serializedProjectSize(project) {
  return new Blob([JSON.stringify(encodeProject(project))]).size;
}
