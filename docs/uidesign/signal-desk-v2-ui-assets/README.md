# Signal Desk V2 UI 资产包

这是根据已确认的 **统一深黑色金融终端风格** 整理的开发复用包。

## 目录

- `screens/`：8 张全尺寸页面参考图，每页单独文件。
- `reference-crops/`：关键区域切片，仅供研发核对布局与视觉，不建议直接作为网页图片使用。
- `icons/svg/`：可直接改色的 24×24 SVG 图标，全部使用 `currentColor`。
- `icons/png/light/`：浅色图标 PNG，适合深黑背景。
- `icons/png/accent/`：品牌绿色图标 PNG。
- `icons/signal-desk-icons.svg`：SVG Symbol Sprite。
- `brand/`：品牌标记、横版 Logo、App Icon、favicon。
- `tokens/`：颜色、边框、字体、动效和 CSS 变量。
- `manifest.json`：资源清单。

## 推荐使用方式

### React / Next.js（直接使用 SVG）

```tsx
import HomeIcon from '@/assets/icons/svg/home.svg';

<HomeIcon className="h-5 w-5 text-slate-300" />
```

### SVG Sprite

```html
<svg width="20" height="20" aria-hidden="true">
  <use href="/assets/icons/signal-desk-icons.svg#sd-risk-shield" />
</svg>
```

### CSS Token

```css
@import './tokens/signal-desk.css';
```

## 图标说明

图标不是从概念图中直接硬裁像素，而是按照页面风格重新整理为干净矢量版本。这样在 16px、20px、24px 和高 DPI 屏幕上不会发虚，也方便前端统一改色与控制描边。

## 页面背景统一规范

- 页面底色：`#020609`
- 侧边栏：`#03090E`
- 基础面板：`#071119`
- 抬升面板：`#0A151E`
- 普通边框：`#1B2B36`
- 品牌绿色：`#00C979`
- 涨：`#00C979`
- 跌：`#F04452`

## 注意

这些页面是高保真视觉参考，不应整张切图直接铺进产品。生产实现应使用组件、真实文本、真实图表和 SVG 图标，以保证响应式、可访问性和清晰度。
