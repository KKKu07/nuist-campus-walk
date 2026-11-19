import {build} from 'esbuild';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
process.chdir(fileURLToPath(new URL('.',import.meta.url)));
const result=await build({entryPoints:['game.js'],bundle:true,minify:true,format:'iife',legalComments:'eof',write:false});
const bundle=result.outputFiles[0].text;
await writeFile('game.bundle.js',bundle);
let html=await readFile('index.html','utf8');
for(const css of ['game.css','campus-hud.css']){
 const style=await readFile(css,'utf8');html=html.replace('<link rel="stylesheet" href="'+css+'">',()=>'<style>'+style+'</style>');
}
const icon=await readFile('icon.svg');
html=html.replace('href="icon.svg"','href="data:image/svg+xml;base64,'+icon.toString('base64')+'"');
html=html.replace('<script src="game.bundle.js"></script>',()=>'<script>'+bundle.replace(/<\/script/gi,'<\\/script')+'</script>');
await mkdir('dist',{recursive:true});await writeFile('dist/校园漫游.html',html);
