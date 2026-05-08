# QR Code Generator Frontend Prototype

## Overview

Develop a high-performance, single-page application (SPA) for dynamic QR Code generation. The system emphasizes Real-time State Synchronization, intuitive Parameter Customization, and high-fidelity visual feedback.

## Layout Structure

- Viewport Constraints: Max-width 1200px (Desktop), horizontally centered.
- Composition:
- Header: Brand Identity & Repository link (GitHub).
- Main Workspace (Grid/Flex):
  - Control Plane (Left - 60%): Configuration Accordions for parameter input.
  - Preview Plane (Right - 40%): Sticky positioned viewport for real-time QR rendering and Action Group (Export/Download).
- Responsive Strategy: Mobile-First implementation using Tailwind CSS breakpoints.

## Component Deep Dive & UX Logic

### Data Input Module (URL/Content)

- Input Validation: Implement String Length Constraints with real-time character count indicators.
- Submission Logic: Integrated Debounce (300ms-500ms) on input to prevent API rate-limiting during rapid typing.
- Interaction State: Upon submission, the component enters a Disabled State (Grayscale filter) with a Loading Spinner overlaying the primary action text.

### Logo Integration Engine (Uploader)

- User Flow: Drag-and-Drop / Native File Explorer → Binary Data Processing → Thumbnail Preview Generation → Context Update.

- Technical Constraints (UX Logic):MIME Type Filtering: Strict whitelist [.png, .jpg, .webp].
- Payload Limit: Client-side validation for files < 2MB.
- Algorithmic Auto-Correction: When a logo is active, programmatically force the Error Correction Level (ECL) to High (H) to ensure scan integrity.
- Scaling Logic: Normalized Slider (0.1 - 0.25 scale) relative to the QR container size.
- Memory Management: Proper cleanup of ObjectURLs on logo removal to prevent memory leaks.

### Styling & Configuration Panel

- Color Schema: RGBA/Hex dual-mode color pickers for Foreground/Background nodes.
- Dimensionality: Synchronized Slider and Numeric Input for pixel-perfect sizing.
- Export Pipeline: Dropdown menu for MIME type selection (image/png, image/svg+xml, image/webp).

## Visual Identity & State Machine

- Design Language: Minimalist aesthetics, high-contrast borders, and low-elevation box-shadows (Shadow-sm).
- Lifecycle States:
  - Idle/Empty: Display a Generic Placeholder or Skeleton screen in the preview area.
  - Loading: Global/Component-level Skeleton Screens with pulse animations during initial hydration or heavy API calls.
  - Success Hook: On successful asset generation, trigger a Micro-interaction (Subtle Jitter/Shake) followed by a Confetti Animation to signify completion.
  - Error Handling: Exception catching via Toast Notifications (Success/Warning/Error).

## Suggested Tech Stack

- Build Tool: Vite (React + TypeScript)
- State Management: TanStack Query (v5) for Server-state caching and synchronization.
- Networking: Axios with Interceptors for global error handling.
- UI Components: Shadcn/UI (Radix UI primitives) + Tailwind CSS.
- Animation: Framer Motion (for the success feedback and jitter effects).
