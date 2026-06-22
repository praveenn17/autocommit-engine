/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // GitHub dark theme palette (exact match)
        canvas: {
          DEFAULT: '#0d1117',
          inset:   '#010409',
          subtle:  '#161b22',
          overlay: '#0d1117',
        },
        border: {
          DEFAULT: '#30363d',
          muted:   '#21262d',
        },
        fg: {
          DEFAULT: '#e6edf3',
          muted:   '#8b949e',
          subtle:  '#6e7681',
          onEmphasis: '#ffffff',
        },
        accent: {
          fg:        '#58a6ff',
          emphasis:  '#1f6feb',
          muted:     'rgba(56,139,253,0.15)',
        },
        success: {
          fg:        '#3fb950',
          emphasis:  '#238636',
          muted:     'rgba(63,185,80,0.15)',
          // GitHub contribution colours
          l0: '#161b22',
          l1: '#0e4429',
          l2: '#006d32',
          l3: '#26a641',
          l4: '#39d353',
        },
        danger: {
          fg:        '#f85149',
          emphasis:  '#da3633',
          muted:     'rgba(248,81,73,0.15)',
        },
        attention: {
          fg:        '#d29922',
          emphasis:  '#9e6a03',
          muted:     'rgba(187,128,9,0.15)',
        },
        done: {
          fg:        '#a371f7',
          emphasis:  '#8957e5',
          muted:     'rgba(163,113,247,0.15)',
        },
      },
      fontFamily: {
        sans: ['"Inter"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      animation: {
        'pulse-slow':   'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':      'fadeIn 0.3s ease-out',
        'slide-up':     'slideUp 0.4s ease-out',
        'shimmer':      'shimmer 1.5s infinite linear',
        'spin-slow':    'spin 2s linear infinite',
        'bounce-once':  'bounceOnce 0.5s ease',
        'glow':         'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        bounceOnce: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-8px)' },
        },
        glow: {
          '0%':   { boxShadow: '0 0 5px rgba(63,185,80,0.4)' },
          '100%': { boxShadow: '0 0 20px rgba(63,185,80,0.8)' },
        },
      },
      backgroundImage: {
        'shimmer-gradient': 'linear-gradient(90deg, transparent 25%, rgba(255,255,255,0.05) 50%, transparent 75%)',
        'grid-pattern':     'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.05) 1px, transparent 0)',
      },
      backgroundSize: {
        'shimmer': '200% 100%',
        'grid':    '24px 24px',
      },
    },
  },
  plugins: [],
}
