import { defineConfig } from 'vite';

// GitHub Pages serves this app from a repository subpath, so all built
// asset URLs must be relative rather than absolute.
export default defineConfig({
  base: './',
});
