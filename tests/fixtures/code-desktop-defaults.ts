/* Pinned upstream schema excerpt; Copyright Microsoft Corporation. MIT. */
const { isLinux } = globalThis.__livaraTestPlatform;
export const schemas = {
			'window.titleBarStyle': {
				'type': 'string',
				'enum': ['native', 'custom'],
				'default': 'custom',
			},
			'window.controlsStyle': {
				'type': 'string',
				'enum': ['native', 'custom', 'hidden'],
				'default': 'native',
			}
};
