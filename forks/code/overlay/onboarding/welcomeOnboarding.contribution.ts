/* SPDX-License-Identifier: MIT
 * Livara uses its own local welcome studio instead of account/agent onboarding.
 */
import { Event } from '../../../../base/common/event.js';
import { InstantiationType, registerSingleton } from '../../../../platform/instantiation/common/extensions.js';
import { IOnboardingService } from '../common/onboardingService.js';

class LivaraOnboarding implements IOnboardingService {
    declare readonly _serviceBrand: undefined;
    readonly onDidDismiss: Event<void> = Event.None;
    show(): void { /* The Livara welcome extension provides local onboarding. */ }
}

// StartupPage still injects this service, even when account/AI onboarding is disabled.
registerSingleton(IOnboardingService, LivaraOnboarding, InstantiationType.Delayed);
