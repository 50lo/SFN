// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://sfn-spec.pages.dev',
	integrations: [
		starlight({
			title: 'Step Flow Notation',
			description: 'A concise text format for describing multi-step AI workflows.',
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/50lo/SFN' }],
			sidebar: [
				{
					label: 'Docs',
					items: [
						{ label: 'Home', slug: 'index' },
						{ label: 'Specification', slug: 'specification' },
					],
				},
			],
		}),
	],
});
