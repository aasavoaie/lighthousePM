const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");

const assetsDirectory = path.resolve(__dirname, "../assets");
const size = 256;

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, checksum]);
}

function setPixel(pixels, x, y, color) {
  if (x < 0 || y < 0 || x >= size || y >= size) {
    return;
  }
  const index = (y * size + x) * 4;
  pixels[index] = color[0];
  pixels[index + 1] = color[1];
  pixels[index + 2] = color[2];
  pixels[index + 3] = color[3];
}

function fillRoundedRect(pixels, left, top, width, height, radius, color) {
  const right = left + width - 1;
  const bottom = top + height - 1;
  for (let y = top; y <= bottom; y += 1) {
    for (let x = left; x <= right; x += 1) {
      const dx = x < left + radius ? left + radius - x : x > right - radius ? x - (right - radius) : 0;
      const dy = y < top + radius ? top + radius - y : y > bottom - radius ? y - (bottom - radius) : 0;
      if (dx * dx + dy * dy <= radius * radius) {
        setPixel(pixels, x, y, color);
      }
    }
  }
}

function fillRect(pixels, left, top, width, height, color) {
  for (let y = top; y < top + height; y += 1) {
    for (let x = left; x < left + width; x += 1) {
      setPixel(pixels, x, y, color);
    }
  }
}

function fillPolygon(pixels, points, color) {
  const minY = Math.max(0, Math.floor(Math.min(...points.map((point) => point[1]))));
  const maxY = Math.min(size - 1, Math.ceil(Math.max(...points.map((point) => point[1]))));

  for (let y = minY; y <= maxY; y += 1) {
    const intersections = [];
    for (let index = 0; index < points.length; index += 1) {
      const current = points[index];
      const next = points[(index + 1) % points.length];
      if ((current[1] <= y && next[1] > y) || (next[1] <= y && current[1] > y)) {
        intersections.push(current[0] + ((y - current[1]) * (next[0] - current[0])) / (next[1] - current[1]));
      }
    }
    intersections.sort((left, right) => left - right);
    for (let index = 0; index < intersections.length; index += 2) {
      const start = Math.max(0, Math.ceil(intersections[index]));
      const end = Math.min(size - 1, Math.floor(intersections[index + 1]));
      for (let x = start; x <= end; x += 1) {
        setPixel(pixels, x, y, color);
      }
    }
  }
}

function createPng() {
  const pixels = Buffer.alloc(size * size * 4);
  fillRoundedRect(pixels, 12, 12, 232, 232, 42, [14, 34, 58, 255]);
  fillPolygon(pixels, [[128, 63], [221, 100], [128, 123]], [252, 211, 77, 235]);
  fillPolygon(pixels, [[128, 63], [35, 100], [128, 123]], [47, 185, 140, 235]);
  fillRect(pixels, 105, 69, 46, 24, [255, 255, 255, 255]);
  fillPolygon(pixels, [[96, 204], [160, 204], [149, 101], [107, 101]], [246, 248, 252, 255]);
  fillRect(pixels, 111, 123, 34, 14, [47, 185, 140, 255]);
  fillRect(pixels, 113, 155, 30, 13, [22, 54, 92, 255]);
  fillRect(pixels, 85, 205, 86, 15, [47, 185, 140, 255]);

  const scanlines = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y += 1) {
    const scanlineOffset = y * (size * 4 + 1);
    scanlines[scanlineOffset] = 0;
    pixels.copy(scanlines, scanlineOffset + 1, y * size * 4, (y + 1) * size * 4);
  }

  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8;
  header[9] = 6;
  header[10] = 0;
  header[11] = 0;
  header[12] = 0;

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", zlib.deflateSync(scanlines, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function createIco(png) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(1, 4);

  const directory = Buffer.alloc(16);
  directory[0] = 0;
  directory[1] = 0;
  directory[2] = 0;
  directory[3] = 0;
  directory.writeUInt16LE(1, 4);
  directory.writeUInt16LE(32, 6);
  directory.writeUInt32LE(png.length, 8);
  directory.writeUInt32LE(header.length + directory.length, 12);

  return Buffer.concat([header, directory, png]);
}

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect x="12" y="12" width="232" height="232" rx="42" fill="#0e223a"/>
  <path d="M128 63 221 100 128 123Z" fill="#fcd34d" opacity=".92"/>
  <path d="M128 63 35 100 128 123Z" fill="#2fb98c" opacity=".92"/>
  <rect x="105" y="69" width="46" height="24" fill="#fff"/>
  <path d="M96 204h64l-11-103h-42Z" fill="#f6f8fc"/>
  <rect x="111" y="123" width="34" height="14" fill="#2fb98c"/>
  <rect x="113" y="155" width="30" height="13" fill="#16365c"/>
  <rect x="85" y="205" width="86" height="15" fill="#2fb98c"/>
</svg>
`;

fs.mkdirSync(assetsDirectory, { recursive: true });
const png = createPng();
fs.writeFileSync(path.join(assetsDirectory, "icon.png"), png);
fs.writeFileSync(path.join(assetsDirectory, "icon.ico"), createIco(png));
fs.writeFileSync(path.join(assetsDirectory, "icon.svg"), svg, "utf8");
console.log("Generated desktop/assets/icon.png, icon.ico, and icon.svg");
