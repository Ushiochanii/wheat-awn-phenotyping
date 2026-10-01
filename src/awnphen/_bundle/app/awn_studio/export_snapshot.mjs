export async function buildHydratedProjectSnapshot(
  project,
  {
    includeImages = false,
    includeInference = false,
    loadAsset = async () => null,
    loadInference = async () => null,
    normalizeInference = value => value
  } = {}
) {
  const pages = [];

  for (const original of project?.pages ?? []) {
    const page = {...original};

    if (
      includeImages &&
      !page.sourcePageId &&
      !page.src &&
      page.assetRef
    ) {
      const source = await loadAsset(page.assetRef);
      if (!source) {
        throw new Error('Stored image asset ' + page.assetRef + ' is missing.');
      }
      page.src = source;
    }

    if (
      includeInference &&
      !page.inference &&
      page.inferenceRef
    ) {
      const stored = await loadInference(page.inferenceRef);
      if (!stored) {
        throw new Error(
          'Stored inference result ' + page.inferenceRef + ' is missing.'
        );
      }
      page.inference = normalizeInference(stored);
    }

    pages.push(page);
  }

  return {...project, pages};
}
