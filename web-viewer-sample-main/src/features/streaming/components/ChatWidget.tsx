/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 */

import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './ChatWidget.css';
import i18n from '../../../i18n';
import { useModalAccessibility } from '../hooks/useModalAccessibility';
import { sendMessage } from '../messaging';
import { aiLanguageFor } from '../../../services/aiLanguage';
import { beginViewTransition } from '../viewTransition';

interface ChatMessage {
	role: 'user' | 'assistant' | 'system';
	text: string;
	id?: string;
	poiId?: string;
	spawnpointName?: string;
	suggestedAction?: string;
	action?: {
		actionId: string;
		tool: string;
		arguments: any;
	};
}

interface ChatWidgetProps {
	isActive: boolean;
	onCustomEvent?: (event: any) => void;
}

const DEFAULT_WELCOME = "I'm a tour guide for Gothenburg. I can help you explore locations like Gothia Towers, Skandinavium, or the Art Museum. What would you like to see?";

const ChatWidget: React.FC<ChatWidgetProps> = ({ isActive, onCustomEvent }) => {
	const { t } = useTranslation();
	const [open, setOpen] = useState(false);
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const [input, setInput] = useState('');
	const [typing, setTyping] = useState(false);
	const sessionIdRef = useRef<string>(`sess_${Math.random().toString(36).slice(2)}`);
	const inputRef = useRef<HTMLInputElement>(null);
	const chatPanelRef = useRef<HTMLDivElement>(null);
	const chatBodyRef = useRef<HTMLDivElement>(null);
	const isInputFocusedRef = useRef<boolean>(false);

	useModalAccessibility(chatPanelRef, { enabled: open });

	// Show default welcome message when user first opens the chat (matches Kit ai_service default)
	useEffect(() => {
		if (open && messages.length === 0) {
			setMessages([{ role: 'assistant', text: DEFAULT_WELCOME }]);
		}
	}, [open, messages.length]);

	useEffect(() => {
		const onToggle = () => setOpen(prev => !prev);
		const handleCustomEvent = (evt: any) => {
			try {
				if (!evt || !evt.event_type) return;

				const chatEventTypes = ['ai.chat.typing', 'ai.chat.done', 'ai.chat.response', 'ai.action.suggestion'];
				if (!chatEventTypes.includes(evt.event_type)) return;

				
				if (evt.event_type === 'ai.chat.typing') {
					setTyping(true);
				} else if (evt.event_type === 'ai.chat.done') {
					setTyping(false);
				} else if (evt.event_type === 'ai.chat.response') {
					setTyping(false);
					const text = evt.payload?.text ?? evt.text ?? '';
					if (!text) return;
					const poiId = evt.payload?.poiId ?? evt.poiId;
					const spawnpointName = evt.payload?.spawnpointName ?? evt.spawnpointName;
					const suggestedAction = evt.payload?.suggestedAction ?? evt.suggestedAction;
					setMessages(prev => [...prev, { role: 'assistant', text, poiId, spawnpointName, suggestedAction }]);
				} else if (evt.event_type === 'ai.action.suggestion') {
					const text = evt.payload?.text ?? evt.text ?? 'The assistant suggests an action.';
					const actionId = evt.payload?.actionId ?? evt.actionId;
					const tool = evt.payload?.tool ?? evt.tool;
					const args = evt.payload?.arguments ?? evt.arguments;
					setMessages(prev => [...prev, { role: 'assistant', text, action: { actionId, tool, arguments: args } }]);
				}
			} catch (error) {
				console.error('Error handling custom event:', error);
			}
		};

		window.addEventListener('toggleChat', onToggle as any);
		// Register custom event handler if provided (Events 2.0 in Omniverse 109.0.2)
		if (onCustomEvent) {
			onCustomEvent(handleCustomEvent);
		}
		return () => {
			window.removeEventListener('toggleChat', onToggle as any);
		};
	}, [onCustomEvent]);

	// Auto-focus input when chat opens and send pause message
	useEffect(() => {
		if (open && inputRef.current) {
			setTimeout(() => {
				inputRef.current?.focus();
				sendMessage('movementInputControl', { enabled: false });
			}, 100);
		} else if (!open) {
			sendMessage('movementInputControl', { enabled: true });
		}
	}, [open]);

	// Auto-scroll chat to bottom when messages or typing indicator change
	useEffect(() => {
		if (!open) return;
		const el = chatBodyRef.current;
		if (!el) return;
		// Defer to next frame to ensure DOM has rendered new nodes
		requestAnimationFrame(() => {
			try {
				el.scrollTop = el.scrollHeight;
			} catch {}
		});
	}, [messages, typing, open]);

	const send = () => {
		const text = input.trim();
		if (!text) return;

		setMessages(prev => [...prev, { role: 'user', text }]);
		setTyping(true);
		setInput('');

		sendMessage('ai.chat.request', {
			text,
			sessionId: sessionIdRef.current,
			language: aiLanguageFor(i18n.language),
		});
		
		setTimeout(() => {
			inputRef.current?.focus();
			sendMessage('movementInputControl', { enabled: false });
		}, 50);
	};

	const handleInputFocus = () => {
		isInputFocusedRef.current = true;
		sendMessage('movementInputControl', { enabled: false });
	};

	const handleInputBlur = () => {
		isInputFocusedRef.current = false;
		if (open) sendMessage('movementInputControl', { enabled: true });
	};

	const confirm = (actionId?: string) => {
		if (!actionId) return;
		sendMessage('ai.action.confirm', { actionId, sessionId: sessionIdRef.current });
	};

	const cancel = (actionId?: string) => {
		sendMessage('ai.action.cancel', { actionId: actionId ?? '', sessionId: sessionIdRef.current });
	};

	// Handle CTA (Yes/No) to avoid repeating prompts
	const handleMoveYes = (index: number, m: ChatMessage) => {
		// Dismiss CTA for this message
		setMessages(prev => {
			const next = [...prev];
			const original = next[index];
			if (original) {
				next[index] = { ...original, suggestedAction: undefined, spawnpointName: undefined };
			}
			return next;
		});
		// Notify backend that user accepted navigation and then request teleport
		try {
			const fallbackSpawn = m.spawnpointName || (m.poiId ? `spawnpoint_${m.poiId}` : undefined);
			beginViewTransition({
				target: 'firstPerson',
				message: i18n.t('streaming.switchingFirstPerson'),
				onFadeOutComplete: () => {
					sendMessage('chat.moveAccepted', { poiId: m.poiId, spawnpointName: fallbackSpawn });
					sendMessage('chat.moveToSpawnpoint', { spawnpointName: fallbackSpawn, poiId: m.poiId });
					sendMessage('teleportToSpawnpoint', { spawnpointName: fallbackSpawn, poiId: m.poiId });
				},
			});
		} catch (e) {
			console.warn('Failed to emit move acceptance/teleport', e);
		}
	};

	const handleMoveNo = (index: number) => {
		// Dismiss CTA for this message and add a single acknowledgement
		setMessages(prev => {
			const next = [...prev];
			const original = next[index];
			if (original) {
				next[index] = { ...original, suggestedAction: undefined, spawnpointName: undefined };
			}
			return [...next, { role: 'assistant', text: "Okay — just say the word if you'd like to go." }];
		});
	};

	if (!isActive) return null;

	return (
		<div className={`chat-widget ${open ? 'open' : ''}`}>
			{open && (
				<div
					ref={chatPanelRef}
					className="chat-panel"
					onKeyDown={(e) => {
						// Stop propagation to prevent WebRTC from capturing keyboard events
						if (inputRef.current && document.activeElement === inputRef.current) {
							// Allow normal input handling, but prevent WebRTC from getting it
							e.stopPropagation();
						}
					}}
					onKeyUp={(e) => {
						if (inputRef.current && document.activeElement === inputRef.current) {
							e.stopPropagation();
						}
					}}
				>
					<div className="chat-header">
						<span>{t('streaming.chatTourGuideTitle')}</span>
						<button
							type="button"
							className="chat-close-btn"
							onClick={() => setOpen(false)}
							aria-label={t('streaming.closeChat')}
						>
							×
						</button>
					</div>
					<div className="chat-body" ref={chatBodyRef}>
						{messages.map((m, i) => (
							<div key={i} className={`msg ${m.role}`}>
								<div className="bubble">{m.text}</div>
								{m.action && (
									<div className="action">
										<button type="button" onClick={() => confirm(m.action?.actionId)}>{t('streaming.chatConfirm')}</button>
										<button type="button" onClick={() => cancel(m.action?.actionId)}>{t('streaming.chatCancel')}</button>
									</div>
								)}
							</div>
						))}
						{/* Dev-only (ai_chat_extension / Ollama): move CTA — not production CU chat (AvatarChatOverlay). */}
						{messages.map((m, i) => (
							(m.role === 'assistant' && m.suggestedAction === 'moveToLocation' && m.spawnpointName) ? (
								<div key={`cta-${i}`} className="cta-block">
									<div className="cta-question">Do you want me to take you there?</div>
									<div className="cta-buttons">
										<button
											type="button"
											className="cta-btn cta-yes"
											onClick={() => handleMoveYes(i, m)}
										>
											Yes
										</button>
										<button
											type="button"
											className="cta-btn cta-no"
											onClick={() => handleMoveNo(i)}
										>
											No
										</button>
									</div>
								</div>
							) : null
						))}
						{/* Typing indicator */}
						{typing && (
							<div
								className="msg assistant"
								role="status"
								aria-live="polite"
								aria-atomic="true"
								aria-label={t('streaming.chatTyping')}
							>
								<div className="bubble typing-bubble" aria-hidden="true">
									<div className="typing-dots">
										<span className="dot"></span>
										<span className="dot"></span>
										<span className="dot"></span>
									</div>
								</div>
							</div>
						)}
					</div>
					<form
						className="chat-input"
						onSubmit={(e) => {
							e.preventDefault();
							// Prevent WebRTC from capturing the submit Enter event
							// by stopping native propagation as early as possible
							// @ts-ignore
							e.nativeEvent?.stopImmediatePropagation?.();
							e.stopPropagation();
							send();
						}}
					>
						<input
							ref={inputRef}
							type="text"
							name="chatMessage"
							autoComplete="off"
							aria-label={t('streaming.chatInputLabel')}
							value={input}
							onChange={(e) => setInput(e.target.value)}
							placeholder={t('streaming.chatInputPlaceholder')}
							onKeyDownCapture={(_e) => {
								// Stop at native level first if available
								// @ts-ignore
								_e.nativeEvent?.stopImmediatePropagation?.();
								_e.stopPropagation();
							}}
							onClick={() => inputRef.current?.focus()}
							onKeyUpCapture={(_e) => {
								// @ts-ignore
								_e.nativeEvent?.stopImmediatePropagation?.();
								_e.stopPropagation();
							}}
							onFocus={handleInputFocus}
							onBlur={handleInputBlur}
						/>
						<button
							type="submit"
							aria-label={t('avatar.sendMessage')}
							onMouseDown={(e) => {
								// Prevent input from losing focus when clicking Send button
								e.preventDefault();
							}}
						>
							Send
						</button>
					</form>
				</div>
			)}
		</div>
	);
};

export default ChatWidget;



