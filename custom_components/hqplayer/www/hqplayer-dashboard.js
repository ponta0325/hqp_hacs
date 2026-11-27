class HQPlayerDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    const view = await HQPlayerDashboardStrategy.generateView({ config, hass });
    return {
      title: config?.title || "HQPlayer",
      views: [view],
    };
  }

  static async generateView(info) {
    const { hass } = info || {};
    const states = hass?.states || {};
    const entityIds = Object.keys(states);

    const findEntity = (domain, suffix) =>
      entityIds.find(
        (id) => id.startsWith(`${domain}.`) && id.endsWith(suffix)
      );

    const playbackState = findEntity("sensor", "_playback_state");
    const inFmt = findEntity("sensor", "_input_format");
    const inRate = findEntity("sensor", "_input_sample_rate");
    const inBit = findEntity("sensor", "_input_bit_depth");
    const outFmt = findEntity("sensor", "_output_format");
    const outRate = findEntity("sensor", "_output_sample_rate");
    const outBit = findEntity("sensor", "_output_bit_depth");
    const apod = findEntity("sensor", "_apodization_count");
    const clips = findEntity("sensor", "_clips_count");

    const outputMode = findEntity("select", "_output_mode");
    const filter1x = findEntity("select", "_filter_1x");
    const filterNx = findEntity("select", "_filter_nx");
    const shaper = findEntity("select", "_shaper_modulator");
    const matrix = findEntity("select", "_matrix_profile");
    const volume = findEntity("number", "_volume");
    const refresh = findEntity("button", "_refresh");

    const cards = [];

    if (inFmt && outFmt) {
      cards.push({
        type: "markdown",
        text_only: true,
        content: [
          `{%- set st = states('${playbackState}') -%}`,
          `{%- set in_fmt = states('${inFmt}') -%}`,
          `{%- set in_rate = states('${inRate}') -%}`,
          `{%- set in_bit = states('${inBit}') -%}`,
          `{%- set out_fmt = states('${outFmt}') -%}`,
          `{%- set out_rate = states('${outRate}') -%}`,
          `{%- set out_bit = states('${outBit}') -%}`,
          `{%- set apod = states('${apod}') -%}`,
          `{%- set clips = states('${clips}') | int(0) -%}`,
          `**{{ st | capitalize }}** — {% if in_fmt in ['unknown', 'unavailable', 'none', ''] -%}Idle{%- else -%}{{ in_fmt }} {{ in_rate }}/{{ in_bit }}{%- endif %}`,
          `→ {{ out_fmt }} {{ out_rate }}/{{ out_bit }}`,
          ``,
          `Apod {{ apod }} / {% if clips > 0 %}<font color="#ff5252"><b>Clips {{ clips }}</b></font>{% else %}Clips {{ clips }}{% endif %}`,
        ].join("\n"),
      });
    }

    const addSelectTile = (entity, name, icon) => {
      if (!entity) return;
      const card = {
        type: "tile",
        entity,
        name,
        hide_state: true,
        vertical: false,
        features_position: "inline",
        features: [{ type: "select-options" }],
      };
      if (icon) card.icon = icon;
      cards.push(card);
    };

    addSelectTile(outputMode, "Output Mode", "mdi:swap-horizontal");
    addSelectTile(filter1x, "Filter 1x");
    addSelectTile(filterNx, "Filter Nx");
    addSelectTile(shaper, "Shaper / Modulator");
    addSelectTile(matrix, "Matrix", "mdi:equalizer");

    if (volume) {
      cards.push({
        type: "tile",
        entity: volume,
        name: "Volume",
        vertical: false,
        features_position: "inline",
        features: [{ type: "numeric-input", style: "slider" }],
      });
    }

    if (refresh) {
      cards.push({
        type: "tile",
        entity: refresh,
        name: "Refresh",
        vertical: false,
      });
    }

    if (cards.length === 0) {
      cards.push({
        type: "markdown",
        content: "No HQPlayer entities found. Please configure the HQPlayer integration first.",
      });
    }

    return {
      title: "HQPlayer",
      path: "hqplayer",
      cards: [
        {
          type: "vertical-stack",
          title: "HQPlayer",
          cards,
        },
      ],
    };
  }
}

class HQPlayerViewStrategy extends HTMLElement {
  static async generate(config, hass) {
    return HQPlayerDashboardStrategy.generateView({ config, hass });
  }
}

if (!customElements.get("ll-strategy-dashboard-hqplayer-dashboard")) {
  customElements.define(
    "ll-strategy-dashboard-hqplayer-dashboard",
    HQPlayerDashboardStrategy
  );
}

if (!customElements.get("ll-strategy-view-hqplayer-dashboard")) {
  customElements.define(
    "ll-strategy-view-hqplayer-dashboard",
    HQPlayerViewStrategy
  );
}

window.customStrategies = window.customStrategies || [];
if (!window.customStrategies.some((s) => s.type === "hqplayer-dashboard")) {
  window.customStrategies.push({
    type: "hqplayer-dashboard",
    strategyType: "dashboard",
    name: "HQPlayer Dashboard",
    description: "Auto-generated dashboard for HQPlayer Control API integration.",
  });
}
