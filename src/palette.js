// 校园地表色板（地表观感 2026-11-27）: one set of surface colours shared by the ground shader (world.js GROUND_LC), the
// road / sidewalk / curb / footpath geometry (world.js buildRoads, buildJunctions) and the canvas paving textures
// (textures.js roadTextures), so a near texture, the same surface seen from 300 m and the road mesh next to it agree.
// sRGB albedo (the sun + sky light them roughly x1.3 on screen). Reference: summer campus photos and the drone
// orthophotos (light grey granite plazas, white-ish sidewalk tiles, muted red permeable brick, dark asphalt).
export const GROUND = {
  lawn: '#5f7b3c',       // mown lawn (Grass005 photo detail on top)
  lawnDry: '#7d8748',    // worn / drier patches, mixed in at a 60 m scale
  shade: '#4a5f33',      // ground cover under trees and in planting beds (麦冬 / 沿阶草 type), leaf litter patches
  soil: '#77654f',       // bare soil, leaf litter
  stone: '#9f9d97',      // light grey granite slabs (芝麻灰): plazas, footpaths, yards
  stoneDark: '#707274',  // dark granite bands and patterns in plazas
  tile: '#bebdb6',       // light sidewalk tiles (user: main-road sidewalks are white tiles)
  brick: '#985a4b',      // red permeable brick paths
  plaza: '#bc9f63',      // ochre / yellow coloured plaza paving
  asphalt: '#4b4d50',    // campus asphalt (public roads a little darker, see textures.js)
  curb: '#b6b4ad',       // granite kerbs
  rubber: '#9a3f33', turf: '#4d873a', court: '#4f7d8c',
};
