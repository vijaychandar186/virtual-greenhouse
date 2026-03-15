# Tailwind CSS Setup Using the CLI

This guide explains the simplest and fastest way to get up and running with Tailwind CSS using the Tailwind CLI tool.

> 💡 The Tailwind CLI is also available as a standalone executable if you want to use it without installing Node.js.

---

## 1. Install Tailwind CSS

Install `tailwindcss` and `@tailwindcss/cli` via npm:

```bash
npm install tailwindcss @tailwindcss/cli
```

---

## 2. Import Tailwind in Your CSS

Create a CSS file (e.g., `input.css`) and add the following import:

```css
@import "tailwindcss";
```

---

## 3. Start the Tailwind CLI Build Process

Run the CLI tool to scan your source files for classes and generate your CSS output:

```bash
npx @tailwindcss/cli -i ./input.css -o ./output.css --watch
```

This command watches your source files and automatically rebuilds `output.css` when changes are detected.

---

## 4. Start Using Tailwind in Your HTML

Create an HTML file (e.g., `index.html`) and link the generated CSS file:

```html
<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="./output.css" rel="stylesheet">
</head>
<body>
  <h1 class="text-3xl font-bold underline">
    Hello world!
  </h1>
</body>
</html>
```

---