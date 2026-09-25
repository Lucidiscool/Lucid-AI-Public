# Appearance

Studio is the default Apple-inspired light theme. Open **Appearance** in the top bar to choose Studio, Midnight, Ocean, Forest, Rose, or Dusk. Accent color, compact spacing, and soft corners can be adjusted separately. **Reset to Studio** restores the defaults.

The **Liquid glass** slider adjusts frosted transparency, backdrop blur, reflections, shadows, and ambient color from 0 (off) to 100 (full glass). It updates live and saves with your theme. The default is 65%. Theme descriptions also accept `liquid glass`, `subtle glass`, and `glass off`. Browsers without backdrop-filter support keep opaque panels for readability. Checked slider endpoints, keyboard control, reload persistence, and light/dark rendering on desktop and at 390px phone width.

Use the description box or type `/theme dark purple` in chat. Descriptions are interpreted locally using supported color and style keywords, not sent to an AI model. Examples: `minimal Apple white`, `ocean blue compact`, `forest soft corners`, and `dark purple`. Six-digit hex colors are also accepted. Unsupported descriptions leave the theme unchanged and show guidance.

Preferences are stored in this browser's local storage under `lucid-appearance-v1`; they do not sync between devices. No backend or new dependency is required. The existing Pages workflow copies the additional CSS and JavaScript with the website assets.

Validation: JavaScript syntax checks and browser checks at 1440×900, 390×844, and 320×640. Verified theme description application, reload persistence, reset, unsupported descriptions, mobile navigation, and absence of horizontal overflow at 320px. UI preview used an empty mock chat state; live model generation was not tested as part of this appearance change.
