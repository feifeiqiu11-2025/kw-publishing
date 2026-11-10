#!/usr/bin/env tsx
/**
 * Generate Story PDF (Node-side) — one-off export for a given story ID.
 *
 * Uses the same StorybookTemplateLarge component the UI uses, but renders
 * server-side with @react-pdf/renderer's renderToFile(). Queries Supabase
 * directly via service role — bypasses RLS and ownership checks.
 *
 * Usage:
 *   npx tsx scripts/generate-story-pdf.tsx <storyId> [storyId2] [--format=large] [--layout=classic] [--out=./out]
 *
 * Defaults: format=large (Legal 7"x8.5"), layout=classic, out=./pdf-exports
 */

import { createClient } from '/Users/feifeiq/Projects/StoryMe.AI/storyme-app/node_modules/@supabase/supabase-js';
import { pdf } from '/Users/feifeiq/Projects/StoryMe.AI/storyme-app/node_modules/@react-pdf/renderer';
import { StorybookTemplateLarge } from '/Users/feifeiq/Projects/StoryMe.AI/storyme-app/src/components/pdf/StorybookTemplateLarge';
import { StorybookTemplate } from '/Users/feifeiq/Projects/StoryMe.AI/storyme-app/src/components/pdf/StorybookTemplate';
import { StorybookTemplateA4 } from './TemplateA4Local';
import { StorybookTemplateComic } from '/Users/feifeiq/Projects/StoryMe.AI/storyme-app/src/components/pdf/StorybookTemplateComic';
import { StorybookTemplateGrid } from '/Users/feifeiq/Projects/StoryMe.AI/storyme-app/src/components/pdf/StorybookTemplateGrid';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join, resolve } from 'path';

// ─── Load .env.local ─────────────────────────────────────────────────
function loadEnv() {
  const envPath = '/nonexistent';
  if (!existsSync(envPath)) return;
  const content = readFileSync(envPath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
    if (value.startsWith("'") && value.endsWith("'")) value = value.slice(1, -1);
    if (!process.env[key]) process.env[key] = value;
  }
}
loadEnv();

// ─── Parse CLI args ──────────────────────────────────────────────────
type Format = 'a5' | 'a4' | 'large';
type Layout = 'classic' | 'comic' | 'grid';

interface Args {
  storyIds: string[];
  format: Format;
  layout: Layout;
  out: string;
}

function parseArgs(): Args {
  const args: Args = {
    storyIds: [],
    format: 'large',
    layout: 'classic',
    out: resolve(__dirname, '../../pdf-exports'),
  };

  for (const arg of process.argv.slice(2)) {
    if (arg.startsWith('--format=')) {
      args.format = arg.slice('--format='.length) as Format;
    } else if (arg.startsWith('--layout=')) {
      args.layout = arg.slice('--layout='.length) as Layout;
    } else if (arg.startsWith('--out=')) {
      args.out = resolve(arg.slice('--out='.length));
    } else if (!arg.startsWith('--')) {
      args.storyIds.push(arg);
    }
  }

  if (args.storyIds.length === 0) {
    console.error('Usage: npx tsx scripts/generate-story-pdf.tsx <storyId> [storyId2...] [--format=large] [--layout=classic] [--out=./pdf-exports]');
    process.exit(1);
  }

  return args;
}

// ─── Fetch story from Supabase ───────────────────────────────────────
interface SceneRow {
  scene_number: number;
  description: string | null;
  caption: string | null;
  caption_chinese: string | null;
  caption_secondary: string | null;
  generated_images: Array<{ image_url: string }> | null;
}

interface CharacterLink {
  is_primary: boolean;
  order_index: number;
  character: {
    name: string;
    designer_name: string | null;
    reference_image_url: string | null;
    animated_preview_url: string | null;
  } | null;
}

interface ProjectRow {
  id: string;
  title: string;
  description: string | null;
  cover_image_url: string | null;
  author_name: string | null;
  author_age: number | null;
  created_at: string;
  scenes: SceneRow[] | null;
  characters: CharacterLink[] | null;
}

async function fetchStory(id: string) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error('Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in env');
  }
  const supabase = createClient(url, key);

  const { data, error } = await supabase
    .from('projects')
    .select(`
      id,
      title,
      description,
      cover_image_url,
      author_name,
      author_age,
      created_at,
      scenes (
        scene_number,
        description,
        caption,
        caption_chinese,
        caption_secondary,
        generated_images ( image_url )
      ),
      characters:project_characters (
        is_primary,
        order_index,
        character:character_library (
          name,
          designer_name,
          reference_image_url,
          animated_preview_url
        )
      )
    `)
    .eq('id', id)
    .single();

  if (error) throw error;
  return data as unknown as ProjectRow;
}

// ─── Map to StoryData ────────────────────────────────────────────────
function buildStoryData(project: ProjectRow) {
  const scenes = (project.scenes || [])
    .filter((s) => s.generated_images && s.generated_images.length > 0)
    .filter((s, i, arr) => {
      // LOCAL PRINT FIX: prod has duplicate scene rows; keep one per scene_number,
      // preferring the photo-page image (the original upload)
      const same = arr.filter((o) => o.scene_number === s.scene_number);
      const pick = same.find((o) => o.generated_images![0].image_url.includes('photo-page')) || same[0];
      return s === pick;
    })
    .sort((a, b) => a.scene_number - b.scene_number)
    .map((s) => ({
      sceneNumber: s.scene_number,
      caption: s.caption || s.description || '',
      caption_chinese: s.caption_chinese || undefined,
      caption_secondary: s.caption_secondary || s.caption_chinese || undefined,
      description: s.description || undefined,
      imageUrl: s.generated_images![0].image_url,
    }));

  const characters = (project.characters || [])
    .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0))
    .map((pc) => ({
      name: pc.character?.name || 'Unknown',
      designerName: pc.character?.designer_name || undefined,
      originalCreationUrl: pc.character?.reference_image_url || undefined,
      storyVersionUrl: pc.character?.animated_preview_url || undefined,
    }));

  let authorString = project.author_name || '';
  if (authorString && project.author_age) authorString += `, age ${project.author_age}`;

  return {
    title: project.title,
    description: project.description || undefined,
    // Fall back to the first scene image so the cover never renders the
    // blue text-only fallback page.
    coverImageUrl: project.cover_image_url || scenes[0]?.imageUrl || undefined,
    scenes,
    characters,
    createdDate: new Date(project.created_at).toLocaleDateString(),
    author: authorString || undefined,
  };
}

// ─── Render PDF ──────────────────────────────────────────────────────
const PAGE_SIZES: Record<Format, { width: number; height: number }> = {
  a5: { width: 420, height: 595 },
  a4: { width: 595, height: 842 },
  large: { width: 504, height: 612 },
};

async function renderPdf(storyData: ReturnType<typeof buildStoryData>, format: Format, layout: Layout): Promise<Buffer> {
  const templateProps = {
    ...storyData,
    pageSize: PAGE_SIZES[format],
  };

  let doc;
  if (layout === 'comic') {
    doc = StorybookTemplateComic(templateProps);
  } else if (layout === 'grid') {
    doc = StorybookTemplateGrid(templateProps);
  } else {
    const Template =
      format === 'a4' ? StorybookTemplateA4 :
      format === 'large' ? StorybookTemplateLarge :
      StorybookTemplate;
    doc = Template(templateProps);
  }

  const instance = pdf(doc);
  // toBuffer returns a Node stream; collect it into a Buffer
  const stream = await instance.toBuffer();
  const chunks: Buffer[] = [];
  return new Promise((res, rej) => {
    stream.on('data', (c: Buffer) => chunks.push(c));
    stream.on('end', () => res(Buffer.concat(chunks)));
    stream.on('error', rej);
  });
}

// ─── Main ────────────────────────────────────────────────────────────
async function main() {
  const args = parseArgs();
  if (!existsSync(args.out)) mkdirSync(args.out, { recursive: true });

  console.log(`[pdf] format=${args.format} layout=${args.layout} out=${args.out}`);

  for (const id of args.storyIds) {
    console.log(`\n[pdf] Fetching story ${id}...`);
    try {
      const project = await fetchStory(id);
      if (!project) {
        console.error(`[pdf] Story ${id} not found`);
        continue;
      }
      const storyData = buildStoryData(project);
      console.log(`[pdf]   title="${storyData.title}" scenes=${storyData.scenes.length} characters=${storyData.characters?.length || 0}`);

      if (storyData.scenes.length === 0) {
        console.error(`[pdf]   ⚠ No scenes with images — skipping`);
        continue;
      }

      const buf = await renderPdf(storyData, args.format, args.layout);
      const safeTitle = storyData.title.replace(/[\\/:*?"<>|]/g, '_');
      const outPath = join(args.out, `${safeTitle} (${id.slice(0, 8)}).pdf`);
      writeFileSync(outPath, buf);
      console.log(`[pdf]   ✓ Wrote ${outPath} (${(buf.length / 1024).toFixed(1)} KB)`);
    } catch (err) {
      console.error(`[pdf] Error for ${id}:`, err instanceof Error ? err.message : err);
    }
  }
}

main().catch((err) => {
  console.error('[pdf] Fatal:', err);
  process.exit(1);
});
