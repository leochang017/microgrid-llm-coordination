import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// SvelteKit config lives here rather than in a svelte.config.js: with
// @sveltejs/vite-plugin-svelte 7 the kit options are passed inline to the plugin.
// The demo is a fully static, prerendered site — no backend, no runtime API.
export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			adapter: adapter(),

			prerender: {
				entries: ['/', '/run/clean', '/run/defectors', '/run/noise', '/run/comm']
			}
		})
	]
});
