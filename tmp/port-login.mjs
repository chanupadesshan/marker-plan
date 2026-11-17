import fs from 'node:fs';
import postcss from '../frontend/node_modules/.pnpm/postcss@8.5.30/node_modules/postcss/lib/postcss.js';
const html=fs.readFileSync('C:/Users/chanupa.d/Downloads/marker_plan_delete_icons_replaced (2).html','utf8');
const css=[...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m=>m[1]).join('\n');
const root=postcss.parse(css);
const generic=/\.(brand(?:-mark|-name)?|feature(?:-list|-icon)?|field|btn(?:-primary|-block)?|login-help)(?![\w-])/;
root.walkRules(rule=>{
 if(rule.parent.type==='atrule'&&/keyframes$/.test(rule.parent.name))return;
 const selectors=rule.selectors.filter(s=> /#loginScreen|\.login-/.test(s)||generic.test(s)||/^(\*|body|:root|button|input|select|textarea)(?:$|[,:\s])/.test(s));
 if(!selectors.length){rule.remove();return;}
 rule.selectors=selectors.map(s=>{
  s=s.replace(/\.login-hero h1/g,'.login-hero h2').replace(/\.login-card h2/g,'.login-card h1');
  if(s===':root'||s==='body')return '#loginScreen';
  return s.includes('#loginScreen')?s:'#loginScreen '+s;
 });
});
root.walkAtRules(at=>{if(at.name==='media'&&!at.nodes.length)at.remove();});
root.walkComments(c=>c.remove());
fs.writeFileSync('frontend/src/login-motion.css','/* Login styles from the supplied HTML, scoped to the real sign-in form. */\n'+root.toString());

