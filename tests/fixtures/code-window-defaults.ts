/* Pinned upstream excerpt: Copyright Microsoft Corporation. MIT license.
 * Fixture executes the actual shared default accessors after Livara patches.
 */
import { isMacintosh, isNative, isTahoeOrNewer, isWeb } from '../../../base/common/platform.js';
type TitlebarStyle = 'native' | 'custom';
type WindowControlsStyle = 'native' | 'custom' | 'hidden';
const TitlebarStyle = { NATIVE: 'native', CUSTOM: 'custom' };
const WindowControlsStyle = { NATIVE: 'native', CUSTOM: 'custom', HIDDEN: 'hidden' };
interface IConfigurationService { getValue<T>(name: string): T; }
interface IWindowSettings { titleBarStyle?: TitlebarStyle; controlsStyle?: WindowControlsStyle; nativeTabs?: boolean; nativeFullScreen?: boolean; }

export function getTitleBarStyle(configurationService: IConfigurationService): TitlebarStyle {
	if (isWeb) {
		return TitlebarStyle.CUSTOM;
	}

	const configuration = configurationService.getValue<IWindowSettings | undefined>('window');
	if (configuration) {
		const useNativeTabs = isMacintosh && configuration.nativeTabs === true;
		if (useNativeTabs) {
			return TitlebarStyle.NATIVE; // native tabs on macOS do not work with custom title style
		}

		const useSimpleFullScreen = isMacintosh && configuration.nativeFullScreen === false;
		if (useSimpleFullScreen) {
			return TitlebarStyle.NATIVE; // simple fullscreen does not work well with custom title style (https://github.com/microsoft/vscode/issues/63291)
		}

		const style = configuration.titleBarStyle;
		if (style === TitlebarStyle.NATIVE || style === TitlebarStyle.CUSTOM) {
			return style;
		}
	}

	return TitlebarStyle.CUSTOM; // default to custom on all OS
}

export function getWindowControlsStyle(configurationService: IConfigurationService): WindowControlsStyle {
	if (isWeb || isMacintosh || getTitleBarStyle(configurationService) === TitlebarStyle.NATIVE) {
		return WindowControlsStyle.NATIVE; // only supported on Windows/Linux desktop with custom titlebar
	}

	const configuration = configurationService.getValue<IWindowSettings | undefined>('window');
	const style = configuration?.controlsStyle;
	if (style === WindowControlsStyle.CUSTOM || style === WindowControlsStyle.HIDDEN) {
		return style;
	}

	return WindowControlsStyle.NATIVE; // default to native on all OS
}
