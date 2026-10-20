<template>
  <main class="coming-soon" aria-labelledby="page-title">
    <img
      class="brand-name"
      src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
      alt="Deconsta"
      width="220"
      height="43"
    />

    <div class="announcement">
      <div class="message">
        <p class="availability"><span aria-hidden="true"></span> Estamos en camino</p>
        <h1 id="page-title">Pronto estaremos disponibles.</h1>
        <p class="description">
          Una forma clara de autorizar pagos, delegarlos y conservar sus comprobantes.
        </p>
      </div>
      <img
        class="brand-symbol"
        src="/brand/deconsta/logo/deconsta-symbol-white.svg"
        alt=""
        width="420"
        height="420"
      />
    </div>

    <p class="signature">Autoriza. Delega. Deja constancia.</p>
  </main>
</template>

<style>
@font-face {
  font-family: 'Literata';
  src: url('/brand/deconsta/fonts/Literata.woff2') format('woff2');
  font-style: normal;
  font-weight: 200 900;
  font-display: swap;
}

@font-face {
  font-family: 'Manrope';
  src: url('/brand/deconsta/fonts/Manrope.woff2') format('woff2');
  font-style: normal;
  font-weight: 200 800;
  font-display: swap;
}

:root {
  font-family: 'Manrope', sans-serif;
  color: #f1f4f1;
  background: #075a50;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color-scheme: light;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
}

.coming-soon {
  max-width: 1680px;
  min-height: 100svh;
  margin-inline: auto;
  padding: clamp(28px, 5vw, 80px);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 64px;
}

.brand-name {
  display: block;
  width: clamp(168px, 18vw, 220px);
  height: auto;
}

.announcement {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(220px, 1fr);
  align-items: center;
  gap: clamp(32px, 5vw, 88px);
  padding-block: 24px;
}

.availability {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 28px;
  font-size: 15px;
  font-weight: 500;
}

.availability span {
  width: 22px;
  height: 4px;
  background: #da792e;
}

h1 {
  max-width: 11em;
  margin: 0;
  font-family: 'Literata', Georgia, serif;
  font-size: clamp(48px, 6.2vw, 94px);
  font-weight: 500;
  font-optical-sizing: auto;
  line-height: 1.13;
  letter-spacing: -0.045em;
  text-wrap: balance;
}

.description {
  max-width: 36em;
  margin: 32px 0 0;
  font-size: clamp(16px, 1.4vw, 19px);
  line-height: 1.8;
}

.brand-symbol {
  display: block;
  width: 100%;
  height: auto;
  max-width: 460px;
  justify-self: end;
}

.signature {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
}

::selection {
  background: #f1f4f1;
  color: #075a50;
}

@media (max-width: 700px) {
  .coming-soon {
    gap: 48px;
  }

  .announcement {
    grid-template-columns: 1fr;
    gap: 40px;
    padding-block: 0;
  }

  .brand-symbol {
    grid-row: 1;
    width: 160px;
    justify-self: start;
    margin-left: -18px;
  }

  h1 {
    font-size: clamp(42px, 9vw, 62px);
  }
}
</style>
