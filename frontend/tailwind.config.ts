import animate from "tailwindcss-animate";

import type { Config } from "tailwindcss";

export default {
	darkMode: ["class"],
	// Relative to this file, not to wherever the build was started.
	content: {
		relative: true,
		files: ["./index.html", "./src/**/*.{ts,tsx}"],
	},
	prefix: "",
	theme: {
		screens: {
			'xs': '480px',
			'sm': '640px',
			'md': '768px',
			'lg': '1024px',
			'xl': '1280px',
			'2xl': '1536px',
		},
		container: {
			center: true,
			padding: '2rem',
			screens: {
				'2xl': '1400px'
			}
		},
		extend: {
			// One family carries everything, as in the MuhAI language. The old
			// `font-montserrat` / `font-roboto` utilities are kept as aliases so any
			// markup still naming them lands on the same face instead of a fallback.
			fontFamily: {
				sans: ['"Inter Tight"', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
				display: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
				montserrat: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
				roboto: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
				logo: ['Syne', '"Inter Tight"', 'system-ui', 'sans-serif'],
				mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
			},
			colors: {
				border: 'hsl(var(--border))',
				input: 'hsl(var(--input))',
				ring: 'hsl(var(--ring))',
				background: 'hsl(var(--background))',
				foreground: 'hsl(var(--foreground))',
				// The MuhAI palette. canvas is the white card, pg the tinted ground
				// under it, ink the text at any opacity (`text-ink/75`), dark what
				// acts, lime what is live. See the token block in index.css.
				canvas: 'hsl(var(--c-canvas) / <alpha-value>)',
				ink: 'hsl(var(--c-ink) / <alpha-value>)',
				pg: 'hsl(var(--c-pg) / <alpha-value>)',
				'pg-deep': 'hsl(var(--c-pg-deep) / <alpha-value>)',
				dark: 'hsl(var(--c-dark) / <alpha-value>)',
				lime: 'hsl(var(--c-lime) / <alpha-value>)',
				'lime-deep': 'hsl(var(--c-lime-deep) / <alpha-value>)',
				signal: 'hsl(var(--c-signal) / <alpha-value>)',
				'signal-fill': 'hsl(var(--c-signal-fill) / <alpha-value>)',
				// Status, muted to the page (the `.lp-tag` triple). RGB so `/10`
				// opacity modifiers work for tints.
				ok: 'rgb(74 124 51 / <alpha-value>)',
				warn: 'rgb(154 100 32 / <alpha-value>)',
				stop: 'rgb(164 67 58 / <alpha-value>)',
				// Series slots, also exposed as utilities so non-chart UI (dots,
				// legends) can reference the same hues.
				'chart-env': 'var(--chart-env)',
				'chart-soc': 'var(--chart-soc)',
				'chart-gov': 'var(--chart-gov)',
				'chart-alt': 'var(--chart-alt)',
				primary: {
					DEFAULT: 'hsl(var(--primary))',
					foreground: 'hsl(var(--primary-foreground))'
				},
				secondary: {
					DEFAULT: 'hsl(var(--secondary))',
					foreground: 'hsl(var(--secondary-foreground))'
				},
				destructive: {
					DEFAULT: 'hsl(var(--destructive))',
					foreground: 'hsl(var(--destructive-foreground))'
				},
				muted: {
					DEFAULT: 'hsl(var(--muted))',
					foreground: 'hsl(var(--muted-foreground))'
				},
				accent: {
					DEFAULT: 'hsl(var(--c-accent) / <alpha-value>)',
					foreground: 'hsl(var(--accent-foreground))'
				},
				popover: {
					DEFAULT: 'hsl(var(--popover))',
					foreground: 'hsl(var(--popover-foreground))'
				},
				card: {
					DEFAULT: 'hsl(var(--c-card) / <alpha-value>)',
					foreground: 'hsl(var(--card-foreground))'
				},
				sidebar: {
					DEFAULT: 'hsl(var(--sidebar-background))',
					foreground: 'hsl(var(--sidebar-foreground))',
					primary: 'hsl(var(--sidebar-primary))',
					'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
					accent: 'hsl(var(--sidebar-accent))',
					'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
					border: 'hsl(var(--sidebar-border))',
					ring: 'hsl(var(--sidebar-ring))'
				}
			},
			borderRadius: {
				lg: 'var(--radius)',
				md: 'calc(var(--radius) - 2px)',
				sm: 'calc(var(--radius) - 4px)'
			},
			keyframes: {
				'accordion-down': {
					from: {
						height: '0'
					},
					to: {
						height: 'var(--radix-accordion-content-height)'
					}
				},
				'accordion-up': {
					from: {
						height: 'var(--radix-accordion-content-height)'
					},
					to: {
						height: '0'
					}
				},
				'fade-in': {
					'0%': {
						opacity: '0',
						transform: 'translateY(20px)'
					},
					'100%': {
						opacity: '1',
						transform: 'translateY(0)'
					}
				},
				'scale-in': {
					'0%': {
						opacity: '0',
						transform: 'scale(0.95)'
					},
					'100%': {
						opacity: '1',
						transform: 'scale(1)'
					}
				},
				'float': {
					'0%, 100%': {
						transform: 'translateY(0px)'
					},
					'50%': {
						transform: 'translateY(-10px)'
					}
				},
				'blob': {
					'0%': {
						transform: 'translate(0px, 0px) scale(1)'
					},
					'33%': {
						transform: 'translate(30px, -50px) scale(1.1)'
					},
					'66%': {
						transform: 'translate(-20px, 20px) scale(0.9)'
					},
					'100%': {
						transform: 'translate(0px, 0px) scale(1)'
					}
				}
			},
			animation: {
				'accordion-down': 'accordion-down 0.2s ease-out',
				'accordion-up': 'accordion-up 0.2s ease-out',
				'fade-in': 'fade-in 0.6s ease-out forwards',
				'scale-in': 'scale-in 0.6s ease-out forwards',
				'float': 'float 3s ease-in-out infinite',
				'blob': 'blob 7s infinite'
			},
			backgroundImage: {
				'gradient-radial': 'radial-gradient(ellipse at center, var(--tw-gradient-stops))',
				'grid-pattern': 'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.1) 1px, transparent 0)'
			},
			backgroundSize: {
				'grid': '20px 20px'
			}
		}
	},
	plugins: [animate],
} satisfies Config;
