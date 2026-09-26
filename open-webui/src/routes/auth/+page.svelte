<script lang="ts">
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';

	import { toast } from 'svelte-sonner';

	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { getBackendConfig } from '$lib/apis';
	import {
		ldapUserSignIn,
		getSessionUser,
		userSignIn,
		userSignUp,
		updateUserTimezone
	} from '$lib/apis/auths';

        import { WEBUI_API_BASE_URL, WEBUI_BASE_URL, withBasePath } from '$lib/constants';
	import { WEBUI_NAME, config, user, socket } from '$lib/stores';

	import { generateInitialsImage, canvasPixelTest, getUserTimezone } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import OnBoarding from '$lib/components/OnBoarding.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import AuthHero from '$lib/components/bizgpt/auth/AuthHero.svelte';
	import AssistantCard from '$lib/components/bizgpt/auth/AssistantCard.svelte';
	import { redirect } from '@sveltejs/kit';

	const i18n = getContext('i18n');

	let loaded = false;

	let mode = $config?.features.enable_ldap ? 'ldap' : 'signin';

	let form = null;

	let name = '';
	let email = '';
	let password = '';
	let confirmPassword = '';

	let ldapUsername = '';

	let submitting = false;

	const setSessionUser = async (sessionUser, redirectPath: string | null = null) => {
		if (sessionUser) {
			console.log(sessionUser);
			toast.success($i18n.t(`You're now logged in.`));
			if (sessionUser.token) {
				localStorage.token = sessionUser.token;
			}
			$socket.emit('user-join', { auth: { token: sessionUser.token } });
			await user.set(sessionUser);
			await config.set(await getBackendConfig());

			// Update user timezone
			const timezone = getUserTimezone();
			if (sessionUser.token && timezone) {
				updateUserTimezone(sessionUser.token, timezone);
			}

                        if (!redirectPath) {
                                redirectPath = $page.url.searchParams.get('redirect') || '/dashboard'; // Biz GPT: land on the dashboard
                        }

                        goto(withBasePath(redirectPath));
			localStorage.removeItem('redirectPath');
		}
	};

	const signInHandler = async () => {
		const sessionUser = await userSignIn(email, password).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		await setSessionUser(sessionUser);
	};

	const signUpHandler = async () => {
		if ($config?.features?.enable_signup_password_confirmation) {
			if (password !== confirmPassword) {
				toast.error($i18n.t('Passwords do not match.'));
				return;
			}
		}

		const sessionUser = await userSignUp(name, email, password, generateInitialsImage(name)).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);

		await setSessionUser(sessionUser);
	};

	const ldapSignInHandler = async () => {
		const sessionUser = await ldapUserSignIn(ldapUsername, password).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
		await setSessionUser(sessionUser);
	};

	const submitHandler = async () => {
		if (submitting) {
			return;
		}

		submitting = true;
		try {
			if (mode === 'ldap') {
				await ldapSignInHandler();
			} else if (mode === 'signin') {
				await signInHandler();
			} else {
				await signUpHandler();
			}
		} finally {
			submitting = false;
		}
	};

	const oauthCallbackHandler = async () => {
		// Get the value of the 'token' cookie
		function getCookie(name) {
			const match = document.cookie.match(
				new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)')
			);
			return match ? decodeURIComponent(match[1]) : null;
		}

		const token = getCookie('token');
		if (!token) {
			return;
		}

		const sessionUser = await getSessionUser(token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (!sessionUser) {
			return;
		}

		localStorage.token = token;
		await setSessionUser(sessionUser, localStorage.getItem('redirectPath') || null);
	};

	let onboarding = false;

	onMount(async () => {
		const redirectPath = $page.url.searchParams.get('redirect');
		const logout = $page.url.searchParams.get('state') === 'logout';

                if ($user && !logout) {
                        goto(withBasePath(redirectPath || '/dashboard')); // Biz GPT: land on the dashboard
		} else {
			if (redirectPath) {
				localStorage.setItem('redirectPath', redirectPath);
			}
		}

		const error = $page.url.searchParams.get('error');
		if (error) {
			toast.error(error);
		}

		await oauthCallbackHandler();
		form = $page.url.searchParams.get('form');

		// Auto-redirect to SSO when OAUTH_AUTO_REDIRECT is enabled and the
		// deployment is unambiguously SSO-only (single provider, no login form,
		// no LDAP). Suppressed after logout, by ?form=, ?error=, onboarding,
		// trusted-header auth, or an existing session/token.
		if ($config?.oauth?.auto_redirect && !logout && !form && !error) {
			const providers = Object.keys($config?.oauth?.providers ?? {});
			if (
				providers.length === 1 &&
				$config?.features?.auth !== false &&
				$config?.features?.enable_login_form === false &&
				!$config?.features?.enable_ldap &&
				!$config?.features?.auth_trusted_header &&
				!$config?.onboarding &&
				!localStorage.token &&
				!document.cookie.split('; ').some((c) => c.startsWith('token='))
			) {
				window.location.href = `${WEBUI_BASE_URL}/oauth/${providers[0]}/login`;
				return;
			}
		}

		loaded = true;

		if (($config?.features?.auth_trusted_header ?? false) || $config?.features?.auth === false) {
			await signInHandler();
		} else {
			onboarding = $config?.onboarding ?? false;
		}
	});
</script>

<svelte:head>
	<!-- LICENSE covers this Biz GPT browser-title identifier.
	Do not alter, remove, obscure, or replace it except as LICENSE permits:
	https://docs.openwebui.com/license. -->
	<title>
		{`${$WEBUI_NAME}`}
	</title>
</svelte:head>

<OnBoarding
	bind:show={onboarding}
	getStartedHandler={() => {
		onboarding = false;
		mode = $config?.features.enable_ldap ? 'ldap' : 'signup';
	}}
/>

<!-- Biz GPT sign-in: decorative hero (left) + sign-in panel (right). Auth logic above is unchanged. -->
<div class="relative h-screen max-h-[100dvh] w-full bg-white dark:bg-gray-950" id="auth-page">
	<div class="drag-region absolute left-0 right-0 top-0 h-8" />

	{#if loaded}
		<div class="grid h-full w-full lg:grid-cols-[minmax(0,1.15fr)_minmax(26rem,1fr)]" id="auth-container">
			<AuthHero name={$WEBUI_NAME} />

			<main class="flex h-full flex-col overflow-y-auto bg-white px-6 py-6 text-gray-900 dark:bg-gray-950 dark:text-gray-100 sm:px-10">
				<!-- top bar -->
				<div class="flex items-center justify-end gap-3 text-sm">
					{#if $config?.features.enable_signup && !($config?.onboarding ?? false) && ($config?.features.enable_login_form || form) && mode !== 'ldap'}
						<span class="text-gray-600 dark:text-gray-400">
							{mode === 'signin' ? `New to ${$WEBUI_NAME}?` : $i18n.t('Already have an account?')}
						</span>
						<button
							type="button"
							class="rounded-xl bg-orange-50 px-4 py-2 font-medium text-orange-600 transition hover:bg-orange-100 dark:bg-orange-500/10 dark:text-orange-300"
							on:click={() => (mode = mode === 'signin' ? 'signup' : 'signin')}
						>
							{mode === 'signin' ? $i18n.t('Sign up') : $i18n.t('Sign in')}
						</button>
					{:else if !($config?.onboarding ?? false)}
						<span class="text-gray-600 dark:text-gray-400">New to {$WEBUI_NAME}?</span>
						<button
							type="button"
							class="rounded-xl bg-orange-50 px-4 py-2 font-medium text-orange-600 transition hover:bg-orange-100 dark:bg-orange-500/10 dark:text-orange-300"
							on:click={() => toast.info('Ask your administrator to create an account for you.')}
						>
							Contact Admin
						</button>
					{/if}
				</div>

				<div class="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-8">
					{#if ($config?.features.auth_trusted_header ?? false) || $config?.features.auth === false}
						<div class="flex items-center justify-center gap-3 text-xl font-normal">
							<div>{$i18n.t('Signing in to {{WEBUI_NAME}}', { WEBUI_NAME: $WEBUI_NAME })}</div>
							<Spinner className="size-5" />
						</div>
					{:else}
						<div id="auth-login-card">
							<div class="flex flex-col items-center text-center">
								<div class="flex items-center gap-3">
									<!-- LICENSE covers this Biz GPT sign-in logo.
									Do not alter, remove, obscure, or replace it except as LICENSE permits:
									https://docs.openwebui.com/license. -->
									<img
										id="logo"
										crossorigin="anonymous"
										src="{WEBUI_BASE_URL}/static/favicon.png"
										class="size-12 rounded-xl"
										alt="{$WEBUI_NAME} logo"
									/>
									<span class="text-3xl font-bold tracking-tight text-[#0f1a3d] dark:text-white">{$WEBUI_NAME}</span>
								</div>

								<h1 class="mt-8 text-3xl font-bold tracking-tight">
									{#if $config?.onboarding ?? false}
										{$i18n.t(`Get started with {{WEBUI_NAME}}`, { WEBUI_NAME: $WEBUI_NAME })}
									{:else if mode === 'signup'}
										Create your account
									{:else}
										Welcome Back
									{/if}
								</h1>
								<p class="mt-2 text-gray-500 dark:text-gray-400">
									{#if $config?.onboarding ?? false}
										Create the first admin account for this workspace
									{:else if mode === 'ldap'}
										{$i18n.t(`Sign in to {{WEBUI_NAME}} with LDAP`, { WEBUI_NAME: $WEBUI_NAME })}
									{:else if mode === 'signup'}
										Sign up to start using your workspace
									{:else}
										Sign in to continue to your workspace
									{/if}
								</p>
								{#if $config?.onboarding ?? false}
									<p class="mt-2 text-xs text-gray-500">
										ⓘ {$WEBUI_NAME}
										{$i18n.t('does not make any external connections, and your data stays securely on your locally hosted server.')}
									</p>
								{/if}
							</div>

							<form
								class="mt-8 flex flex-col"
								on:submit={(e) => {
									e.preventDefault();
									submitHandler();
								}}
							>
								{#if $config?.features.enable_login_form || $config?.features.enable_ldap || form}
									<div class="flex flex-col gap-3.5">
										{#if mode === 'signup'}
											<label class="bz-field">
												<span class="sr-only">{$i18n.t('Name')}</span>
												<svg class="bz-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" /></svg>
												<input bind:value={name} type="text" id="name" class="bz-input" autocomplete="name" placeholder={$i18n.t('Enter Your Full Name')} required />
											</label>
										{/if}

										{#if mode === 'ldap'}
											<label class="bz-field">
												<span class="sr-only">{$i18n.t('Username')}</span>
												<svg class="bz-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" /></svg>
												<input bind:value={ldapUsername} type="text" class="bz-input" autocomplete="username" name="username" id="username" placeholder={$i18n.t('Enter Your Username')} required />
											</label>
										{:else}
											<label class="bz-field">
												<span class="sr-only">{$i18n.t('Email')}</span>
												<svg class="bz-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" /></svg>
												<input bind:value={email} type="email" id="email" class="bz-input" autocomplete="email" name="email" placeholder="Email address" required />
											</label>
										{/if}

										<div class="bz-field">
											<svg class="bz-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>
											<SensitiveInput
												bind:value={password}
												type="password"
												id="password"
												outerClassName="flex flex-1 items-center"
												class="bz-input"
												showButtonClassName="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
												placeholder="Password"
												autocomplete={mode === 'signup' ? 'new-password' : 'current-password'}
												name="password"
												screenReader={true}
												required
												aria-required="true"
											/>
										</div>

										{#if mode === 'signup' && $config?.features?.enable_signup_password_confirmation}
											<div class="bz-field">
												<svg class="bz-field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" /></svg>
												<SensitiveInput
													bind:value={confirmPassword}
													type="password"
													id="confirm-password"
													outerClassName="flex flex-1 items-center"
													class="bz-input"
													showButtonClassName="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
													placeholder={$i18n.t('Confirm Your Password')}
													autocomplete="new-password"
													name="confirm-password"
													required
												/>
											</div>
										{/if}
									</div>

									{#if mode === 'signin'}
										<div class="mt-3 flex justify-end text-sm">
											<button
												type="button"
												class="text-gray-600 transition hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
												on:click={() => toast.info('Ask your administrator to reset your password (Admin → Users).')}
											>
												Forgot password?
											</button>
										</div>
									{/if}

									<button
										class="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-orange-500 to-amber-500 py-3.5 text-base font-semibold text-white shadow-lg shadow-orange-500/25 transition hover:from-orange-600 hover:to-amber-500 disabled:opacity-60"
										type="submit"
										disabled={submitting}
									>
										{#if mode === 'ldap'}
											{$i18n.t('Authenticate')}
										{:else if mode === 'signin'}
											{$i18n.t('Sign In')}
										{:else if $config?.onboarding ?? false}
											{$i18n.t('Create Admin Account')}
										{:else}
											{$i18n.t('Create Account')}
										{/if}
										{#if submitting}
											<Spinner className="size-4" />
										{:else}
											<svg viewBox="0 0 20 20" fill="currentColor" class="size-5" aria-hidden="true"><path fill-rule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.64l-4.22-4.22a.75.75 0 1 1 1.06-1.06l5.5 5.5a.75.75 0 0 1 0 1.06l-5.5 5.5a.75.75 0 1 1-1.06-1.06l4.22-4.22H3.75A.75.75 0 0 1 3 10Z" clip-rule="evenodd" /></svg>
										{/if}
									</button>
								{/if}
							</form>

							{#if Object.keys($config?.oauth?.providers ?? {}).length > 0}
								{#if $config?.features.enable_login_form || $config?.features.enable_ldap || form}
									<div class="my-5 flex items-center gap-3 text-sm text-gray-400">
										<div class="h-px flex-1 bg-gray-200 dark:bg-gray-800"></div>
										{$i18n.t('or')}
										<div class="h-px flex-1 bg-gray-200 dark:bg-gray-800"></div>
									</div>
								{/if}
								<div class="flex flex-col gap-2.5">
									{#each [['google', 'Google'], ['microsoft', 'Microsoft'], ['github', 'GitHub'], ['oidc', $config?.oauth?.providers?.oidc ?? 'SSO'], ['feishu', 'Feishu']] as [key, label]}
										{#if $config?.oauth?.providers?.[key]}
											<button
												type="button"
												class="flex w-full items-center justify-center gap-3 rounded-2xl border border-gray-200 py-3 text-sm font-medium transition hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-900"
												on:click={() => {
													window.location.href = `${WEBUI_BASE_URL}/oauth/${key}/login`;
												}}
											>
												{#if key === 'google'}
													<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" class="size-5" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" /><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" /><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" /><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" /></svg>
												{:else if key === 'microsoft'}
													<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" class="size-5" aria-hidden="true"><rect x="1" y="1" width="9" height="9" fill="#f25022" /><rect x="1" y="11" width="9" height="9" fill="#00a4ef" /><rect x="11" y="1" width="9" height="9" fill="#7fba00" /><rect x="11" y="11" width="9" height="9" fill="#ffb900" /></svg>
												{:else if key === 'github'}
													<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="size-5" aria-hidden="true"><path fill="currentColor" d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.92 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57C20.565 21.795 24 17.31 24 12c0-6.63-5.37-12-12-12z" /></svg>
												{:else if key === 'oidc'}
													<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" /></svg>
												{/if}
												<span>{$i18n.t('Continue with {{provider}}', { provider: label })}</span>
											</button>
										{/if}
									{/each}
								</div>
							{/if}

							{#if $config?.features.enable_ldap && $config?.features.enable_login_form}
								<button
									class="mt-4 w-full text-center text-xs text-gray-500 underline"
									type="button"
									on:click={() => {
										if (mode === 'ldap') mode = ($config?.onboarding ?? false) ? 'signup' : 'signin';
										else mode = 'ldap';
									}}
								>
									{mode === 'ldap' ? $i18n.t('Continue with Email') : $i18n.t('Continue with LDAP')}
								</button>
							{/if}

							<div class="mt-8">
								<AssistantCard />
							</div>
						</div>
					{/if}
				</div>

				{#if $config?.metadata?.login_footer}
					<div class="marked mx-auto max-w-md text-center text-[0.7rem] text-gray-500 dark:text-gray-400">
						{@html DOMPurify.sanitize(marked($config?.metadata?.login_footer))}
					</div>
				{/if}
			</main>
		</div>
	{/if}
</div>

<style>
	:global(#auth-page .bz-field) {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		border-radius: 1rem;
		border: 1px solid rgb(229 231 235);
		padding: 0.95rem 1rem;
		transition: border-color 0.15s, box-shadow 0.15s;
	}
	:global(#auth-page .bz-field:focus-within) {
		border-color: rgb(249 115 22);
		box-shadow: 0 0 0 3px rgb(249 115 22 / 0.15);
	}
	:global(.dark #auth-page .bz-field) {
		border-color: rgb(38 38 38);
	}
	:global(#auth-page .bz-field-icon) {
		width: 1.25rem;
		height: 1.25rem;
		flex-shrink: 0;
		color: rgb(107 114 128);
	}
	:global(#auth-page .bz-input) {
		width: 100%;
		background: transparent;
		font-size: 0.95rem;
		outline: none;
	}
	:global(#auth-page .bz-input::placeholder) {
		color: rgb(156 163 175);
	}
</style>
