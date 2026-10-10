'use strict';
const $=id=>document.getElementById(id);
let journalFilter='all';
let asset=localStorage.getItem('btc-lab-asset')==='ETH'?'ETH':'BTC';
const isEth=()=>asset==='ETH';
const strategyIds=()=>isEth()?['eth-mid-window-v1']:['value-v1','late-v1','early-v1','mid-window-v1'];
const preview=false;
let state=null,connected=false,lang=localStorage.getItem('btc-lab-language')||'pl',selected='value-v1';
const strings={pl:{workspace:'PRZESTRZEŃ ROBOCZA',overview:'Przegląd',strategies:'Strategie',activity:'Aktywność',operations:'Działanie',paperOnly:'Wyłącznie symulacja',noWallet:'Brak połączenia z portfelem. Prawdziwe środki pozostają nietknięte.',title:'Najpierw dowody. Potem ryzyko.',subtitle:'Wyniki, decyzje i stan systemu w jednym miejscu.',preview:'Podgląd interfejsu',export:'↓ Pobierz raport',netPnl:'Zrealizowany wynik testowy',balance:'Dostępne środki wirtualne',winRate:'Skuteczność rozliczonych',dataPoints:'Zapisane obserwacje',afterFees:'Po opłatach transakcyjnych · przed hostingiem',performance:'Wynik strategii 5–15 min',performanceHint:'Skumulowany wynik rozliczonych transakcji · USD',waitingEvidence:'Czekamy na dane',emptyChart:'Wykres pojawi się po co najmniej dwóch zrealizowanych punktach wynikowych.',realised:'Zrealizowany wynik',currentWindow:'Aktualne okno',untilResolution:'do zamknięcia okna',reference:'Cena referencyjna',opening:'Referencja otwarcia',feedAge:'Wiek referencji',strategyComparison:'Porównanie strategii',isolatedAccounts:'Oddzielne konta wirtualne · wspólne zasady wykonania',tradeJournal:'Rejestr transakcji',journalHint:'Każde wykonanie i rozliczenie pozostaje w historii.',time:'CZAS',strategy:'STRATEGIA',cost:'KOSZT + OPŁATY',noTrades:'Brak transakcji testowych',noTradesHint:'Transakcja wymaga poprawnych danych i spełnienia reguł strategii oraz ryzyka.',systemHealth:'Stan systemu',collector:'Zbieranie danych',model:'Model prawdopodobieństwa',trainingData:'Okna z oficjalnym wynikiem',liveOrders:'Prawdziwe zlecenia',disabled:'WYŁĄCZONE',costPlan:'Limit kosztów infrastruktury',budgetHint:'Planowany budżet, nie rachunek. Oddzielnie od kapitału handlowego.',decisionLog:'Rejestr decyzji',skipMatters:'Pominięcie transakcji też jest decyzją.',footer:'Najpierw dowody. Potem kapitał.'}};
const english={};document.querySelectorAll('[data-i18n]').forEach(el=>english[el.dataset.i18n]=el.textContent);
const text=(id,value)=>{const el=$(id);if(el)el.textContent=value==null?'':value;};
const money=(v,signed=false)=>v==null?'—':new Intl.NumberFormat(lang==='pl'?'pl-PL':'en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,signDisplay:signed?'exceptZero':'auto'}).format(v);
const formatTime=t=>new Date(t*1000).toLocaleTimeString(lang==='pl'?'pl-PL':'en-GB',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit'});
const t=(en,pl)=>lang==='pl'?pl:en;
let cardLayout=localStorage.getItem('btc-lab-card-layout')||'auto';
let cardOrder=[];
try{cardOrder=JSON.parse(localStorage.getItem('btc-lab-card-order')||'[]');}catch(e){cardOrder=[];}
if(!Array.isArray(cardOrder))cardOrder=[];
if(localStorage.getItem('btc-lab-card-layout-stamp')!=='20261005-green-top'){
  cardLayout='auto';
  localStorage.setItem('btc-lab-card-layout','auto');
  localStorage.setItem('btc-lab-card-layout-stamp','20261005-green-top');
}
function missing(){return t('no data','brak danych');}
function when(ts){return ts==null?missing():formatTime(ts);}
function rosterLabel(state){
  return ({observed:t('OBSERVED','OBSERWOWANY'),paper_test:t('PAPER TEST','TEST PAPER'),paper_active:t('PAPER ACTIVE','AKTYWNY PAPER'),paused:t('PAUSED','WSTRZYMANY')})[state]||t('NO STATE','BRAK STANU');
}
function intakeLine(w){
  if(!w||w.feed==null)return t('Feed: no data','Odbiór: brak danych');
  if(w.intake==='feed_down'||w.feed==='down')return t('Feed failed','Awaria odbioru danych')+(w.observer_error?' · '+w.observer_error:'');
  if(w.intake==='no_source_trades')return t('No source trades','Brak transakcji źródła');
  if(w.intake==='no_fresh_source_trades')return t('No fresh source trade','Brak świeżej transakcji źródła');
  if(w.intake==='unprocessed')return t('Fresh source trade, no copier decision yet','Świeża transakcja źródła, brak decyzji kopiarki');
  if(w.intake==='receiving'){
    let s=t('Receiving source trades','Odbiór transakcji działa');
    if(w.history_page_capped)s+=' · '+t('older history page capped','starsza historia strony ucięta');
    return s;
  }
  return t('Feed: no data','Odbiór: brak danych');
}
function progressLine(w){
  const p=w&&w.progress;
  if(!p)return t('PAPER test progress: no data','Postęp do testu PAPER: brak danych');
  const settled=p.settled==null?missing():p.settled+'/'+p.need_settled;
  const windows=p.windows==null?missing():p.windows+'/'+p.need_windows;
  const obs=p.observation_days==null?missing():Number(p.observation_days).toFixed(1);
  const ev=!(p.need_days>0)?null:p.evidence_days==null?missing():Number(p.evidence_days).toFixed(1)+'/'+p.need_days;
  const left=[];
  if(p.settled==null)left.push(t('settled copies: no data','rozliczone kopie: brak danych'));
  else if(p.settled<p.need_settled)left.push(t('settled copies short ','rozliczonych kopii brakuje ')+(p.need_settled-p.settled));
  if(p.windows==null)left.push(t('windows: no data','okna: brak danych'));
  else if(p.windows<p.need_windows)left.push(t('windows short ','okien brakuje ')+(p.need_windows-p.windows));
  if(p.need_days>0&&p.evidence_days==null)left.push(t('evidence days: no data','dni dowodu: brak danych'));
  else if(p.need_days>0&&p.evidence_days<p.need_days)left.push(t('evidence days short ','dni dowodu brakuje ')+(p.need_days-p.evidence_days).toFixed(1));
  if(p.net_usd==null)left.push(t('net after costs: no data','netto po kosztach: brak danych'));
  else if(p.net_usd<p.need_net_usd)left.push(t('net below the PAPER test bar','netto poniżej progu testu PAPER'));
  const rest=left.length?left.join(' · '):t('requirements currently met','wymagania obecnie spełnione');
  const concentration=p.best_day_share!=null&&p.max_best_day_share!=null&&p.best_day_share>p.max_best_day_share
    ?' · '+t('One day holds more than 70% of the gains. That is uncertainty, not a block.','Jeden dzień ma ponad 70% zysków. To niepewność, nie blokada.'):'';
  const days=ev?(' · '+t('evidence days','dni dowodu')+' '+ev):'';
  return t('Settled copies','Rozliczone kopie')+' '+settled+' · '+t('windows','okna')+' '+windows+' · '+t('observation days','dni obserwacji')+' '+obs+days+' · '+t('still needed','pozostałe wymagania')+': '+rest+concentration;
}
function copyLedByPaper(account){
  return account.roster_state==='paper_active'||account.roster_state==='paper_test'||account.roster_state==='paused';
}
function hypotheticalExists(w){
  if(!w||w.shadow_known===false)return false;
  return w.hypothetical_open>0||w.hypothetical_settled>0||w.hypothetical_net_usd!=null||w.other_hypothetical_settled>0;
}
function copyStatPairs(account){
  if(copyLedByPaper(account)){
    const pnl=account.pnl==null?missing():money(account.pnl,true);
    const trades=account.trades==null?missing():String(account.trades);
    return [[pnl,t('PAPER account','Konto PAPER')],[trades,t('PAPER trades','Transakcje PAPER')]];
  }
  const w=account.watch||{};
  const net=w.policy_known===false||w.policy_net_usd==null?missing():money(w.policy_net_usd,true);
  const counts=w.policy_known?String(w.policy_open)+' / '+String(w.policy_settled):missing();
  return [[net,t('Policy observation','Obserwacja polityki')],[counts,t('Open / settled','Otwarte / rozliczone')]];
}
function independentLine(w){
  if(!hypotheticalExists(w))return null;
  const hyp=w.hypothetical_net_usd==null?missing():money(w.hypothetical_net_usd,true);
  const other=w.other_hypothetical_settled?(' · '+t('other skips','inne pominięcia')+' '+w.other_hypothetical_settled+' · '+(w.other_net_usd==null?missing():money(w.other_net_usd,true))):'';
  return t('Independent tickets, not a PAPER profit and not a promotion','Niezależne bilety, nie zysk konta PAPER i nie awans')+': '+t('open','otwarte')+' '+String(w.hypothetical_open)+' · '+t('settled','rozliczone')+' '+String(w.hypothetical_settled)+' · '+t('net','netto')+' '+hyp+other;
}
function policyLine(w){
  const version=w&&w.policy_version?w.policy_version:missing();
  const net=!w||!w.policy_known||w.policy_net_usd==null?missing():money(w.policy_net_usd,true);
  const counts=w&&w.policy_known?String(w.policy_open)+' / '+String(w.policy_settled):missing();
  return t('Policy observation','Obserwacja polityki')+' '+version+' · '+t('open / settled','otwarte / rozliczone')+' '+counts+' · '+t('net','netto')+' '+net;
}
function copyWatchLines(account){
  const w=account.watch||{};
  const lines=[
    rosterLabel(account.roster_state)+' · '+intakeLine(w.feed?w:null)+(w.policy_version?' · '+w.policy_version:''),
    t('Last check','Ostatnie sprawdzenie')+': '+when(w.checked_at)+' · '+t('last detected trade','ostatnia wykryta transakcja')+': '+when(w.last_source_at)+' · '+t('last detected buy','ostatni wykryty zakup')+': '+when(w.last_buy_at),
  ];
  if(account.roster_state==='observed')lines.push(progressLine(w));
  if(account.roster_state==='paused')lines.push(policyLine(w));
  const indep=independentLine(w);
  if(indep)lines.push(indep);
  if(account.roster_state==='observed'&&account.trades>0)lines.push(t('PAPER account, separate','Konto PAPER, osobno')+': '+money(account.pnl,true)+' · '+t('paper trades','transakcje PAPER')+': '+account.trades);
  lines.push(t('Last skip reason','Ostatni powód pominięcia')+': '+(w.last_reason?reason(w.last_reason):missing()));
  return lines;
}
function cardKind(account){
  if(account.id.startsWith('copy-'))return rosterLabel(account.roster_state);
  if(isEth()||account.id==='value-surface-paper-v1')return t('EXPERIMENT','EKSPERYMENT');
  return account.id==='value-v1'?t('CANDIDATE','KANDYDAT'):t('BASELINE','BAZOWA');
}
function cardTitle(account){
  if(account.id.startsWith('copy-'))return account.name;
  return ({'value-surface-paper-v1':t('Value Surface · PAPER 100 USD','Value Surface · PAPER 100 USD'),'eth-mid-window-v1':t('ETH 3–7 · PAPER · stop 10%','ETH 3–7 · PAPER · stop 10%'),'value-v1':t('Reference-aware value','Wartość z referencją'),'late-v1':t('Late direction · PAUSED','Późny kierunek · WSTRZYMANA'),'early-v1':t('Early direction','Wczesny kierunek'),'mid-window-v1':t('BTC 3–7 · PAPER · stop 10%','BTC 3–7 · PAPER · stop 10%'),'mid-window-v2':t('BTC 3–7 v2 · PAPER · stop 10%','BTC 3–7 v2 · PAPER · stop 10%')})[account.id]||account.name||account.id;
}
function cardBlurb(account){
  if(account.id.startsWith('copy-'))return t('Hypothetical copies are separate from the PAPER account. A missing figure is “no data”, not a confirmed zero.','Hipotetyczne kopie są osobno od konta PAPER. Brak liczby to „brak danych”, nie potwierdzone zero.');
  return ({'value-surface-paper-v1':t('Independent probabilities by market minute. Delayed fills, fees and 1% maximum entry cost. Unvalidated.','Osobne prawdopodobieństwa dla minut rynku. Opóźnienie, opłaty i maksymalny koszt wejścia 1%. Eksperyment.'),'eth-mid-window-v1':t('New ETH entries: stop 10% net; up to $5 including entry fee. Protective exits also after minute 10; fills not guaranteed.','Nowe wejścia ETH: stop 10% netto; do 5 USD z opłatą zakupu. Sprzedaż ochronna także po 10. minucie; wykonanie niegwarantowane.'),'value-v1':t('Calibrated probability. Cost-aware entries.','Kalibrowane prawdopodobieństwo. Wejścia po kosztach.'),'late-v1':t('Damian-inspired. Rebuilt with common accounting.','Inspiracja Damianem. Wspólne zasady księgowania.'),'early-v1':t('New entries: stop at 10% net loss; execution not guaranteed.','Nowe wejścia: stop przy stracie 10% netto; wykonanie niegwarantowane.'),'mid-window-v1':t('Buy 3–7 min · 50–80¢ · stop 10% net. Protective sales can continue after minute 10.','Zakup 3–7 min · 50–80¢ · stop 10% netto. Sprzedaż ochronna także po 10. minucie.'),'mid-window-v2':t('Buy 3–7 min · 50–80¢ · stop 10% net. Protective sales can continue after minute 10.','Zakup 3–7 min · 50–80¢ · stop 10% netto. Sprzedaż ochronna także po 10. minucie.')})[account.id]||'';
}
function cardResult(account){
  if(account.id.startsWith('copy-')){
    if(copyLedByPaper(account))return account.trades>0&&Number.isFinite(Number(account.pnl))?Number(account.pnl):null;
    const net=account.watch&&account.watch.policy_known?account.watch.policy_net_usd:null;
    return net!=null&&Number.isFinite(Number(net))?Number(net):null;
  }
  return account.trades>0&&Number.isFinite(Number(account.pnl))?Number(account.pnl):null;
}
function cardToneClass(account){
  const v=cardResult(account);
  if(v==null)return '';
  return v>=0?' profit':' loss';
}
function cardRank(account){
  const v=cardResult(account);
  if(v==null)return 0;
  return v>=0?1e12+v:v;
}
function sortAccounts(list){
  if(cardLayout==='manual'&&cardOrder.length){
    const rank=id=>{const i=cardOrder.indexOf(id);return i<0?1000:i;};
    return list.slice().sort((a,b)=>rank(a.id)-rank(b.id)||cardRank(b)-cardRank(a));
  }
  return list.slice().sort((a,b)=>cardRank(b)-cardRank(a)||String(a.id).localeCompare(String(b.id)));
}
function finite(v){if(v==null||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;}
let journalBook='paper';
let paperPeriod=localStorage.getItem('btc-lab-paper-period')||'all';
let historyPage=Number(localStorage.getItem('btc-lab-history-page')||0);
if(!['today','week','all'].includes(paperPeriod))paperPeriod='all';
function ownStrategies(accounts){return (accounts||[]).filter(a=>!String(a.id).startsWith('copy-'));}
function bookParts(accounts){
  const list=accounts||[];
  const strategy=list.filter(a=>!String(a.id).startsWith('copy-')).reduce((sum,a)=>sum+(finite(a.pnl)||0),0);
  const paper=list.filter(a=>String(a.id).startsWith('copy-')).reduce((sum,a)=>sum+(finite(a.pnl)||0),0);
  let policy=0,policyKnown=0,independent=0,independentKnown=0;
  for(const account of list){
    if(!String(account.id).startsWith('copy-')||!account.watch)continue;
    const watched=finite(account.watch.policy_net_usd);
    if(account.watch.policy_known&&watched!=null){policy+=watched;policyKnown++;}
    const side=finite(account.watch.hypothetical_net_usd);
    if(side!=null){independent+=side;independentKnown++;}
  }
  return {strategy,paper,policy,policyKnown,independent,independentKnown};
}
function rowsFrom(accounts,key,status){
  const extra=[];
  for(const account of accounts||[]){
    for(const row of (account.watch&&account.watch[key])||[]){
      const cost=finite(row.cost_micro);
      const fee=finite(row.fee_micro)||0;
      const pnl=finite(row.pnl_micro);
      extra.push({opened:Number(row.closed_at||row.opened||0),strategy:account.id,side:row.side||'—',cost:cost==null?0:cost,fee,exit_fee:0,cost_known:cost!=null,payout:pnl==null?null:(cost||0)+fee+pnl,pnl_usd:pnl==null?null:pnl/1e6,status,hypothetical:status!=='PAPER'});
    }
  }
  return extra.sort((a,b)=>(b.opened||0)-(a.opened||0)).slice(0,200);
}
function paperBoardOf(s){return s&&s.wallet_copy_execution&&s.wallet_copy_execution.board||null;}
function inPaperPeriod(row,board){
  if(!row||row.closed_at==null)return false;
  if(paperPeriod==='all')return true;
  if(paperPeriod==='week')return row.closed_at>=board.week_start;
  return new Date(row.closed_at*1000).toLocaleDateString('en-CA',{timeZone:'Europe/Stockholm'})===board.today;
}
function journalRows(s){
  const board=paperBoardOf(s);
  if(!board)return [];
  return (board.journal||[]).filter(row=>inPaperPeriod(row,board)).map(row=>({
    opened:row.closed_at,strategy:'copy-'+(row.wallet||''),side:row.side||'—',
    cost:Number(row.cost)||0,fee:Number(row.fee)||0,exit_fee:Number(row.exit_fee)||0,
    payout:row.pnl_micro==null?null:Number(row.cost||0)+Number(row.fee||0)+Number(row.exit_fee||0)+Number(row.pnl_micro),
    status:row.status||'SETTLED',hypothetical:false,pnl_micro:row.pnl_micro,
  }));
}
function openCopyTrades(s){
  const rows=(s&&s.wallet_copy_execution&&s.wallet_copy_execution.recent_trades)||[];
  return rows.filter(row=>row&&(row.status==='OPEN'||row.status==='RESOLVED')).map(row=>({
    opened:Number(row.opened||0),strategy:'copy-'+(row.wallet||''),side:row.side||'—',
    cost:Number(row.cost)||0,fee:Number(row.fee)||0,exit_fee:Number(row.exit_fee)||0,
    payout:null,status:row.status,hypothetical:false,pnl_micro:null,market:row.market||'',open:true,
  })).sort((a,b)=>(b.opened||0)-(a.opened||0));
}
function journalPnl(tr){
  if(tr.hypothetical)return finite(tr.pnl_usd);
  if(tr.payout==null)return null;
  return (tr.payout-tr.cost-tr.fee-(tr.exit_fee||0))/1e6;
}
function journalStatus(tr){
  if(tr.status==='HYPOTHETICAL')return t('INDEPENDENT','NIEZALEŻNA');
  if(tr.status==='POLICY')return t('POLICY OBSERVATION','OBSERWACJA POLITYKI');
  if(tr.status==='OPEN')return t('OPEN · PAPER','OTWARTA · PAPER');
  if(tr.status==='RESOLVED')return t('RESOLVED · PAPER','CZEKA NA WYPŁATĘ · PAPER');
  return tr.status==='CLOSED'?t('SOLD · PAPER','SPRZEDANO · PAPER'):tr.status;
}
function journalLabel(tr,accounts){
  const account=(accounts||[]).find(a=>a.id===tr.strategy);
  let name=tr.strategy;
  if(String(tr.strategy).startsWith('copy-'))name=(account&&account.name)||String(tr.strategy).slice(-8);
  if(tr.status==='HYPOTHETICAL')name+=' · '+t('independent','niezależna');
  if(tr.status==='POLICY')name+=' · '+t('policy','polityka');
  return name;
}
function node(tag,content,cls){const el=document.createElement(tag);if(content!==undefined)el.textContent=content;if(cls)el.className=cls;return el;}
function translate(){document.documentElement.lang=lang;document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=lang==='pl'?(strings.pl[el.dataset.i18n]||english[el.dataset.i18n]):english[el.dataset.i18n]);text('language',lang==='pl'?'EN':'PL');render();renderGuide();installHelp();routeGuide();}
function blank(){return {mode:'PAPER',accounts:strategyIds().map(id=>({id,name:id,cash:null,pnl:null,settled:0,trades:0,wins:0,curve:[]})),trades:[],decisions:[],worker:{},market:{},model:{status:'COLLECTING',samples:0},reference:{},price_history:[]};}
const reasons={COPY_PRICE_TOO_LOW:['Source price below 20 cents — lottery ticket','Cena źródłowa poniżej 20 centów — los'],COPY_PRICE_TOO_HIGH:['Source price above 70 cents — too little upside for a full loss','Cena źródłowa powyżej 70 centów — za mały zysk przy pełnej stracie'],COPY_PAUSED:['This copy wallet is turned off','Ten portfel kopii jest wyłączony'],COPY_POSITION_ALREADY_OPEN:['Copied position still open','Skopiowana pozycja nadal otwarta'],COPY_CASH_LIMIT:['Insufficient copy cash','Za mało środków konta kopii'],COPY_DAY_LOSS_LIMIT:['Copy blocked by 24-hour loss budget','Kopia zablokowana limitem strat 24h'],COPY_WEEK_LOSS_LIMIT:['Copy blocked by 7-day loss budget','Kopia zablokowana limitem strat 7 dni'],RISK_CAPACITY_EXHAUSTED:['Loss budget exhausted','Wyczerpany limit strat'],CAPACITY_BELOW_MARKET_MINIMUM:['Remaining budget below market minimum','Pozostała kwota poniżej minimum rynku'],COPY_BUY_TOO_LATE:['Copy buy older than 10 seconds','Zakup źródłowy starszy niż 10 sekund'],SOURCE_PRICE_MOVED:['Price moved more than 3 cents from source','Cena zmieniła się o ponad 3 centy względem źródła'],COPIED_BUY:['Copied BUY in PAPER','Skopiowano zakup PAPER'],COPIED_SELL:['Copied SELL in PAPER','Skopiowano sprzedaż PAPER'],NO_NEW_SOURCE_TRADE:['No new source trade since activation','Brak nowej transakcji źródłowej od uruchomienia'],PRE_ACTIVATION:['Historical activity; not replayed','Zdarzenie sprzed uruchomienia; bez kopiowania wstecz'],SOURCE_TOO_OLD:['Source trade too old to copy','Transakcja źródłowa zbyt stara do skopiowania'],SOURCE_PRICE_MOVED:['Executable price is more than 10 cents from the source trade','Cena wykonania odbiega o ponad 10 centów od transakcji źródła'],SOURCE_PRICE_MISSING:['Source trade has no usable price','Transakcja źródłowa nie ma wiarygodnej ceny'],RISK_OR_EXISTING_POSITION:['Risk limit or existing copied position','Limit ryzyka lub istniejąca kopia'],NO_COPIED_POSITION:['No matching copied position to sell','Brak odpowiadającej kopii do sprzedaży'],UNSUPPORTED_MARKET:['Outside supported BTC/ETH5m/15m markets','Poza obsługiwanymi rynkami BTC/ETH5m/15m'],BUY_NO_FULL_FILL_OR_MINIMUM:['Insufficient depth or below order minimum','Brak płynności lub zlecenie poniżej minimum'],ABORTED_ON_RESTART:['Interrupted by restart; not replayed','Przerwane restartem; bez odtwarzania'],STRATEGY_RETIRED:['Retired: no new BTC entries; history retained','Wycofana: brak nowych wejść BTC; historia zachowana'],MODEL_SCHEMA_MISMATCH:['Collecting a model for this reference source','Zbieranie modelu dla tego źródła ceny'],REFERENCE_SOURCE_MISMATCH:['Reference source does not match this market','Źródło ceny nie odpowiada regule rynku'],MODEL_COLLECTING:['Building the training dataset','Zbieranie danych do modelu'],RULE_UNVERIFIED:['Market rule needs verification','Reguła rynku wymaga weryfikacji'],OPENING_REFERENCE_MISSING:['Opening reference unavailable','Brak referencji otwarcia'],REFERENCE_STALE:['Reference data is stale','Nieaktualna referencja'],BOOK_STALE:['Order book is stale','Nieaktualny arkusz zleceń'],NO_NET_EDGE:['No edge after costs','Brak przewagi po kosztach'],NO_FULL_FILL:['Insufficient eligible liquidity','Brak wystarczającej płynności'],DISTANCE_TOO_SMALL:['Price too close to opening','Cena zbyt blisko otwarcia'],OUTSIDE_ENTRY_WINDOW:['Outside the entry window','Poza oknem wejścia'],OUTSIDE_MODEL_HORIZON:['Outside the model horizon','Poza horyzontem modelu'],FILLED:['Paper order filled','Zlecenie testowe wykonane'],EXPOSURE_OR_DUPLICATE:['Position already recorded','Pozycja już zarejestrowana'],MANUAL_PAUSE:['Research entries paused','Wejścia testowe wstrzymane'],FEE_UNVERIFIED:['Fee schedule unverified','Niezweryfikowane opłaty'],RISK_LIMIT:['Risk limit reached','Osiągnięto limit ryzyka']};
Object.assign(reasons,{WAITING_VALID_PROBABILITY:['Collecting valid probability estimates','Zbieranie poprawnych oszacowań prawdopodobieństwa'],NO_NET_EDGE_OR_MINIMUM_SIZE:['No net edge or order below minimum','Brak przewagi netto lub zlecenie poniżej minimum'],BUY_PENDING:['Awaiting delayed purchase snapshot','Oczekiwanie na późniejszą cenę zakupu'],SELL_PENDING:['Awaiting delayed sale snapshot','Oczekiwanie na późniejszą cenę sprzedaży'],BOUGHT_PAPER:['Bought in simulation','Kupiono w symulacji'],SOLD_PAPER:['Sold in simulation','Sprzedano w symulacji'],ARRIVAL_REJECTED:['Arrival data or price rejected','Odrzucono dane w chwili wykonania'],BUY_NO_FULL_FILL:['Purchase not fully executable','Brak możliwości pełnego zakupu'],SELL_NO_FULL_FILL:['Sale not fully executable; still holding','Brak możliwości pełnej sprzedaży; pozycja pozostaje'],ALREADY_TRADED_WINDOW:['One entry per window already used','Wykorzystano jedno wejście w tym oknie'],RISK_OR_STALE_BOOK:['Risk limit or stale book','Limit ryzyka lub nieaktualny arkusz'],HOLD_VALUE_OR_NO_DEPTH:['Holding: valuation or insufficient depth','Trzymanie: wycena lub brak płynności'],PAUSED_OR_RECONCILIATION_BLOCK:['Paused or reconciliation incomplete','Pauza lub nieukończone uzgodnienie rozliczeń'],STRATEGY_PAUSED:['New entries turned off','Nowe zakłady wyłączone'],SKIPPED_INACTIVE:['Wallet is not on the live copy list','Ten portfel nie jest na liście kopii']});
function filterJournal(trades,filter){return filter==='all'?trades:trades.filter(tr=>tr.strategy===filter);}
function reason(r){return reasons[r]?.[lang==='pl'?1:0]||r;}
function chart(curve){const svg=$('performance-chart');svg.replaceChildren();const ns='http://www.w3.org/2000/svg';const shape=(tag,attrs)=>{const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));svg.appendChild(e);return e;};for(let i=0;i<5;i++)shape('line',{x1:0,y1:15+i*48,x2:710,y2:15+i*48,stroke:'#23313f','stroke-width':1,'stroke-dasharray':'3 5'});$('chart-empty').hidden=curve.length>=2;if(curve.length<2)return;const values=curve.map(x=>x.pnl).filter(Number.isFinite);if(values.length!==curve.length)return;const low=Math.min(0,...values),high=Math.max(0,...values),range=high-low||1;const coords=values.map((y,i)=>[i/(values.length-1)*705,210-(y-low)/range*190]);const line=coords.map(([x,y],i)=>`${i?'L':'M'} ${x.toFixed(2)} ${y.toFixed(2)}`).join(' ');shape('path',{d:`${line} L 705 220 L 0 220 Z`,fill:'#65d7bc',opacity:.065});shape('path',{d:line,fill:'none',stroke:'#65d7bc','stroke-width':2.4,'stroke-linejoin':'round'});for(let i=0;i<5;i++){const label=shape('text',{x:755,y:20+i*48,fill:'#668096','font-size':10,'text-anchor':'end'});label.textContent=(high-(i/4)*range).toFixed(2);}const last=coords.at(-1);shape('circle',{cx:last[0],cy:last[1],r:4,fill:'#65d7bc'});}
function serviceVersionLabel(worker,live,previewMode,now){if(previewMode)return 'PREVIEW';if(!live||!worker?.version)return '—';const age=now-Number(worker.heartbeat||0);return 'v'+worker.version+(age>=0&&age<30?'':' · STALE');}
function periodTitle(board,key){
  if(!board)return missing();
  if(key==='today')return t('Today ','Dzisiaj ')+(board.today||'')+t(', Stockholm',', Sztokholm');
  if(key==='week')return t('Last 7 days, from ','Ostatnie 7 dni, od ')+(board.week_start?formatTime(board.week_start):missing())+t(' Stockholm',' Sztokholm');
  return t('Whole PAPER copy book','Od początku księgi kopiowania PAPER');
}
function copyScopeNote(){
  return t('Closed PAPER copies after costs. Open positions are separate. 5–15 min strategies are not included.','Zamknięte kopie PAPER po kosztach. Otwarte pozycje są osobno. Strategie 5–15 min nie wchodzą.');
}
function paintNet(id,micro){
  const el=$(id);if(!el)return;
  el.textContent=micro==null?missing():money(micro/1e6,true);
  el.className='metric-value '+(micro==null?'':micro>0?'positive':micro<0?'negative':'');
}
function rowInPeriod(row,board,key){
  if(!row||row.closed_at==null||!board)return false;
  if(key==='all')return true;
  if(key==='week')return row.closed_at>=board.week_start;
  return new Date(row.closed_at*1000).toLocaleDateString('en-CA',{timeZone:'Europe/Stockholm'})===board.today;
}
function reasonTotal(s,name){
  const rows=s.wallet_copy_execution&&s.wallet_copy_execution.reasons;
  if(!Array.isArray(rows))return null;
  let n=0;
  for(const row of rows)if(row.reason===name)n+=Number(row.count)||0;
  return n;
}
function fillPeriodCards(board){
  for(const key of ['today','week','all']){
    const period=board&&board.periods&&board.periods[key];
    const card=$('card-'+key);if(card)card.classList.toggle('on',key===paperPeriod);
    text('label-'+key,periodTitle(board,key));
    paintNet('net-'+key,period?period.net_micro:null);
    const closed=period&&period.closed!=null?String(period.closed):missing();
    text('note-'+key,copyScopeNote()+' · '+closed+' '+t('closed trades','zamkniętych transakcji'));
  }
}
function fillTodayLines(board,s){
  const box=$('today-lines');if(!box)return;
  box.replaceChildren();
  if(!board||!board.periods||!board.periods.today){box.append(node('p',missing()));return;}
  const rows=(board.journal||[]).filter(row=>rowInPeriod(row,board,'today')).sort((a,b)=>a.closed_at-b.closed_at);
  let sum=0,known=true;
  if(!rows.length)box.append(node('p',t('Confirmed zero closed PAPER copies today','Potwierdzone zero zamkniętych kopii PAPER dzisiaj')));
  for(const row of rows){
    if(row.pnl_micro==null)known=false;else sum+=Number(row.pnl_micro);
    const amount=row.pnl_micro==null?missing():money(row.pnl_micro/1e6,true);
    const line=node('p',formatTime(row.closed_at)+' · '+String(row.wallet||'').slice(-8)+' · '+(row.side||'—')+' · '+amount);
    if(row.pnl_micro>0)line.className='positive';else if(row.pnl_micro<0)line.className='negative';
    box.append(line);
  }
  const expected=board.periods.today.net_micro;
  const match=known&&expected!=null&&sum===expected&&rows.length===board.periods.today.closed;
  box.append(node('p',match?t('These trades are the Today number: ','Te transakcje są liczbą Dzisiaj: ')+money(expected/1e6,true):t('This list does not match the Today number','Ta lista nie zgadza się z liczbą Dzisiaj')));
  const opens=openCopyTrades(s);
  if(opens.length){
    box.append(node('p',t('Open copies. They are not in the Today number until they close.','Otwarte kopie. Nie wchodzą do liczby Dzisiaj, dopóki się nie zamkną.')));
    for(const row of opens){
      const line=node('p',formatTime(row.opened)+' · '+String(row.strategy).slice(-8)+' · '+row.side+' · '+t('open','otwarta')+' · '+money((row.cost+row.fee)/1e6));
      box.append(line);
    }
  }
  text('today-scope',t('Stockholm date ','Data Sztokholmu ')+(board.today||'')+'. '+t('Closed PAPER copies are the Today number. Open copies are listed under them.','Zamknięte kopie PAPER są liczbą Dzisiaj. Otwarte kopie są pod nimi.'));
}
function tileRank(row){
  if(!row)return 1e18;
  if(row.net_micro==null)return -1e18;
  const v=Number(row.net_micro);
  return v>=0?1e18+v:v;
}
function watchShort(account){
  const checked=account.watch&&account.watch.checked_at;
  if(checked==null)return t('No check','Brak sprawdzenia');
  const age=Date.now()/1000-Number(checked);
  const clock=formatTime(checked);
  if(age>=0&&age<300)return t('Watched · ','Śledzony · ')+clock;
  return t('Last check · ','Ostatnio · ')+clock;
}
function fillWalletTiles(s,board,period){
  const box=$('wallet-tiles');if(!box)return;
  box.replaceChildren();
  const accounts=(s.accounts||[]).filter(a=>String(a.id).startsWith('copy-'));
  const by={};
  for(const row of (period&&period.wallets)||[])by[row.wallet]=row;
  const opensBy={};
  for(const row of openCopyTrades(s))opensBy[String(row.strategy).replace(/^copy-/,'')]=(opensBy[String(row.strategy).replace(/^copy-/,'')]||0)+1;
  const copyingNow=a=>a.roster_state==='paper_active'||a.roster_state==='paper_test';
  accounts.sort((a,b)=>{
    const aw=copyingNow(a),bw=copyingNow(b);
    if(aw!==bw)return aw?-1:1;
    const ao=opensBy[a.wallet||String(a.id).replace(/^copy-/,'')]||0;
    const bo=opensBy[b.wallet||String(b.id).replace(/^copy-/,'')]||0;
    if((ao>0)!==(bo>0))return ao>0?-1:1;
    return tileRank(by[b.wallet||String(b.id).replace(/^copy-/,'')])-tileRank(by[a.wallet||String(a.id).replace(/^copy-/,'')]);
  });
  let copying=0,idle=0;
  const periodName=paperPeriod==='today'?t('Today','Dzisiaj'):paperPeriod==='week'?t('Last 7 days','Ostatnie 7 dni'):t('From the start','Od początku');
  for(const account of accounts){
    const wallet=account.wallet||String(account.id).replace(/^copy-/,'');
    const row=by[wallet];
    if(account.roster_state==='paper_active'||account.roster_state==='paper_test')copying++;
    if(!(account.trades>0))idle++;
    const known=!!period&&(!!row&&row.net_micro!=null||!row);
    const net=row&&row.net_micro!=null?Number(row.net_micro):known?0:null;
    const copyingZero=copyingNow(account)&&net===0;
    const card=node('article',undefined,'strategy-card wallet-tile'+(net>0?' profit':net<0?' loss':copyingZero?' flat':''));
    card.dataset.strategy='copy-'+wallet;
    const top=node('div',undefined,'strategy-top');
    top.append(node('span',String(wallet).slice(-8),'strategy-number'),node('span',rosterLabel(account.roster_state),'chip'));
    card.append(top);
    const stats=node('div',undefined,'strategy-stats');
    const pnl=node('div');
    const amount=node('strong',net==null?missing():money(net/1e6,true));
    if(net>0)amount.className='positive';else if(net<0)amount.className='negative';
    pnl.append(amount,node('small',periodName+' · PAPER'));
    const closed=node('div');
    const n=!period?missing():row&&row.closed!=null?String(row.closed):'0';
    closed.append(node('strong',n),node('small',t('Closed','Zamknięte')));
    stats.append(pnl,closed);
    card.append(stats,node('p',watchShort(account),'watch-line'));
    const openCount=opensBy[wallet]||0;
    const openCost=(openCopyTrades(s).filter(t=>String(t.strategy).replace(/^copy-/,'')===wallet)
      .reduce((sum,t)=>sum+(Number(t.cost)||0)+(Number(t.fee)||0),0));
    const rosterRow=((s.wallet_roster||{}).wallets||{})[wallet]||{};
    if(rosterRow.state==='paused'&&rosterRow.since){
      const pauseNet=row&&row.pause_period_net_usd!=null?money(Number(row.pause_period_net_usd),true):missing();
      card.append(node('p','Pauza od '+formatTime(rosterRow.since)+' · wynik dnia '+(net==null?missing():money(net/1e6,true))+' · wynik okresu, który wstrzymał zakupy: '+pauseNet+(rosterRow.sample?' · próba '+rosterRow.sample:''),'watch-line'));
    }
    if(account.reserved>0)card.append(node('p','Zarezerwowane '+money(account.reserved)+' · do kolejnych zakupów '+(account.tradable==null?missing():money(account.tradable)),'watch-line'));
    if(openCount)card.append(node('p',t('Open copy','Otwarta kopia')+' · '+openCount+' · koszt '+money(openCost/1e6)+' · '+t('not a closed result','to nie jest zamknięty wynik'),'watch-line'));
    else if(row&&row.pause_reason)card.append(node('p',row.pause_reason,'watch-line'));
    else if(!(account.trades>0))card.append(node('p',t('No closed copy. Watching is not a result.','Brak zamkniętej kopii. Śledzenie nie jest wynikiem.'),'watch-line'));
    card.onclick=()=>{localStorage.setItem('btc-lab-open-wallet',wallet);openWalletDetail(s,account,row,openCount);};
    box.append(card);
  }
  const openId=localStorage.getItem('btc-lab-open-wallet');
  if(openId){
    const account=accounts.find(a=>(a.wallet||String(a.id).replace(/^copy-/,''))===openId);
    if(account){
      const wallet=account.wallet||String(account.id).replace(/^copy-/,'');
      openWalletDetail(s,account,by[wallet],opensBy[wallet]||0);
    }
  }
  text('wallet-track',periodName+' · '+t('watched ','śledzone ')+accounts.length+' · '+t('copying now ','kopiujemy teraz ')+copying+' · '+t('no closed copy ','bez zamkniętej kopii ')+idle+'. '+t('Copying wallets first, then green. 5–15 min strategies are on their own tab.','Najpierw kopiowane, potem zielone. Strategie 5–15 min są na osobnej zakładce.'));
}
function fillPriceBand(s){
  const high=reasonTotal(s,'COPY_PRICE_TOO_HIGH');
  const low=reasonTotal(s,'COPY_PRICE_TOO_LOW');
  const buys=reasonTotal(s,'COPIED_BUY');
  const fmt=n=>n==null?missing():String(n);
  text('price-band-counts',t('Rejected above 70¢: ','Odrzucone powyżej 70¢: ')+fmt(high)+'. '+t('Rejected below 20¢: ','Odrzucone poniżej 20¢: ')+fmt(low)+'. '+t('Copied buys: ','Skopiowane zakupy: ')+fmt(buys)+'.');
  text('price-band-note',t('The 20–70¢ band is a limit of this PAPER version. A 75¢ source buy is rejected by that limit. That is not a claim that 75¢ is automatically a losing trade. Changing the band belongs in a separate PAPER. This copy is not Mitch’s system.','Pasmo 20–70¢ jest limitem tej wersji PAPER. Zakup źródła za 75¢ odpada przez ten limit. To nie jest teza, że 75¢ jest z góry stratnym zakupem. Zmiana pasma należy do osobnego PAPER. To kopiowanie nie jest systemem Mitcha.'));
  text('copy-rules',t('Copy rules, paper-roster-v3. Observation becomes a test after 20 settled copies, 5 windows and a positive net. No calendar wait. A day above 70% of the gains is uncertainty, not a block. A known negative net of closed copies opened in the current stint blocks new buys. A missing result is not zero. Open positions stay separate. A sell and settlement still run. Return needs a positive observation opened after the pause. Fewer than 10 such closes is an uncertain sample, and the old losses stay. An added buy stays inside the 5 USD position cap, fees included. A source sell closes our shares by that sell divided by the source position just before it. A missing source size or an incomplete source history leaves the position open.','Reguły kopiowania, paper-roster-v3. Obserwacja staje się testem po 20 rozliczonych kopiach, 5 oknach i dodatnim wyniku. Nie ma blokady kalendarzowej. Dzień powyżej 70% zysków to niepewność, nie blokada. Ujemny, znany wynik zamkniętych kopii otwartych w bieżącym okresie blokuje nowe zakupy. Brak wyniku nie jest zerem. Otwarte pozycje są osobno. Sprzedaż i rozliczenie zostają. Powrót wymaga dodatniej obserwacji otwartej po pauzie. Poniżej 10 takich zamknięć to niepewna próba, a stare straty zostają w księdze. Dokupienie mieści się w limicie 5 USD na pozycję, razem z opłatami. Sprzedaż źródła zamyka taką część naszych udziałów, ile ta sprzedaż stanowi pozycji źródła tuż przed nią. Brak rozmiaru albo niepełna historia źródła zostawia pozycję otwartą.'));
}
function ledgerLine(s){
  const health=s.wallet_copy_health||{};
  if(health.status!=='ledger_mismatch')return '';
  const when=health.last_good_at?formatTime(health.last_good_at):'brak';
  const who=(health.held||[]).join(', ')||'brak portfela';
  return 'WYNIK NIEAKTUALNY · ostatnia poprawna publikacja '+when+' · nowe zakupy wstrzymane dla '+who+' · pozostałe kopiowanie trwa';
}
function renderCopyFlow(s){
  const flow=(s.wallet_copy_execution||{}).flow||{};
  const el=$('copy-flow');
  const held=ledgerLine(s);
  if(held){
    text('copy-flow',held);
    if(el)el.className='data-status stale';
    return;
  }
  const titles={
    copying:['Copying is working','Kopiowanie działa'],
    no_signals:['No new signals','Brak nowych sygnałów'],
    paused:['All buys are paused','Wszystkie zakupy wstrzymane'],
    filtered:['Signals rejected by filters','Sygnały odrzucone przez filtry'],
    feed:['Data reception problem','Problem z odbiorem danych']
  };
  const pair=titles[flow.code];
  if(!pair){
    text('copy-flow',t('Copy status: no data','Stan kopiowania: brak danych'));
    if(el)el.className='data-status stale';
    return;
  }
  const when=flow.last_signal_at?formatTime(flow.last_signal_at):t('none','brak');
  const detail=lang==='en'?flow.detail_en:flow.detail_pl;
  text('copy-flow',t(pair[0],pair[1])+' · '+t('Last signal ','Ostatni sygnał ')+when+(detail?' · '+detail:''));
  if(el)el.className='data-status '+(flow.code==='copying'?'fresh':'stale');
}
function renderPaperBoard(s){
  const board=paperBoardOf(s);
  const outdated=preview||location.hostname.endsWith('github.io')||(connected&&s.view&&s.view!=='live');
  const banner=$('demo-banner');
  if(banner){banner.hidden=!outdated;if(outdated)banner.textContent=t('OUTDATED PREVIEW — these are not the current results of the service on port 8769.','NIEAKTUALNY PODGLĄD — to nie są bieżące wyniki usługi na porcie 8769.');}
  const worker=s.worker||{};
  const age=Date.now()/1000-Number(worker.heartbeat||0);
  const bookAge=board?Date.now()/1000-Number(board.generated_at||0):null;
  const fresh=connected&&!outdated&&age>=0&&age<45&&bookAge!=null&&bookAge>=0&&bookAge<90;
  const stamp=board&&board.generated_at?formatTime(board.generated_at):'';
  renderCopyFlow(s);
  text('data-status',fresh?t('Data current — updated ','Dane aktualne — aktualizacja ')+stamp:t('Data is stale','Dane nieaktualne'));
  const statusEl=$('data-status');if(statusEl)statusEl.className='data-status '+(fresh?'fresh':'stale');
  text('revision-line',s.revision&&/^[0-9a-f]{40}$/.test(s.revision)?'Rewizja '+s.revision:t('Revision: no data','Rewizja: brak danych'));
  document.querySelectorAll('.period-switch button').forEach(btn=>{
    btn.classList.toggle('on',btn.dataset.period===paperPeriod);
    if(btn.dataset.bound)return;
    btn.dataset.bound='1';
    btn.onclick=()=>{paperPeriod=btn.dataset.period;localStorage.setItem('btc-lab-paper-period',paperPeriod);render();};
  });
  const period=board&&board.periods?board.periods[paperPeriod]:null;
  fillPeriodCards(board);fillTodayLines(board,s);fillWalletTiles(s,board,period);fillPriceBand(s);
  text('board-net-label',periodTitle(board,paperPeriod));
  text('table-title',t('Wallets in the selected period','Portfele w wybranym okresie'));
  text('table-scope',periodTitle(board,paperPeriod)+' · '+copyScopeNote());
  const netEl=$('board-net');
  if(netEl){
    netEl.textContent=!period||period.net_micro==null?t('no data','brak danych'):money(period.net_micro/1e6,true);
    netEl.className='metric-value '+(!period||period.net_micro==null?'':period.net_micro>0?'positive':period.net_micro<0?'negative':'');
  }
  text('board-net-note',periodTitle(board,paperPeriod)+'. '+copyScopeNote()+' '+t('The table sum is this number.','Suma tabeli to ta liczba.'));
  const open=board&&board.open;
  const opens=openCopyTrades(s);
  text('board-open-count',!open?t('no data','brak danych'):String(open.count));
  text('board-open-note',!open?t('no data','brak danych'):opens.length?opens.map(row=>String(row.strategy).slice(-8)+' · '+row.side+' · '+formatTime(row.opened)).join(' · '):(open.mark_micro==null?t('No current valuation','brak aktualnej wyceny'):t('Confirmed zero open positions','zero otwartych pozycji — potwierdzone zero')));
  const body=$('board-wallets');
  if(body){
    body.replaceChildren();
    const rows=period?period.wallets||[]:[];
    if(!period){const tr=node('tr');const cell=node('td',t('no data','brak danych'));cell.colSpan=5;tr.append(cell);body.append(tr);}
    else if(!rows.length){const tr=node('tr');const cell=node('td',t('No PAPER copy wallets in this period','W tym okresie nie ma portfeli kopiowania PAPER'));cell.colSpan=5;tr.append(cell);body.append(tr);}
    let sum=0,known=!!(period&&period.net_micro!=null);
    for(const row of rows){
      if(row.net_micro==null)known=false;else sum+=row.net_micro;
      const tr=node('tr');
      const wallet=node('td',String(row.wallet||'').slice(-8));wallet.title=row.wallet||'';
      const netCell=node('td',row.net_micro==null?t('no data','brak danych'):money(row.net_micro/1e6,true));
      if(row.net_micro>0)netCell.className='positive';else if(row.net_micro<0)netCell.className='negative';
      tr.append(wallet,node('td',row.copying?t('Yes','Tak'):t('No','Nie')),netCell,node('td',String(row.closed)),node('td',row.pause_reason||t('not applicable','nie dotyczy')));
      body.append(tr);
    }
    const agree=known&&period&&sum===period.net_micro;
    text('board-sum',!period||period.net_micro==null?t('no data','brak danych'):money(period.net_micro/1e6,true));
    text('board-sum-count',!period||period.closed==null?t('no data','brak danych'):String(period.closed));
    text('board-sum-note',!period?t('no data','brak danych'):agree?t('Matches the result above','Zgadza się z wynikiem u góry'):t('Table sum does not match the result above','Suma tabeli nie zgadza się z wynikiem u góry'));
    const journal=journalRows(s);
    let journalMicro=0,journalKnown=true;
    for(const row of journal){if(row.pnl_micro==null)journalKnown=false;else journalMicro+=Number(row.pnl_micro);}
    const same=!!(period&&period.net_micro!=null&&journalKnown&&journalMicro===period.net_micro&&journal.length===period.closed);
    text('journal-sum',!period?t('no data','brak danych'):same?t('Journal sum matches the main result: ','Suma dziennika zgadza się z wynikiem głównym: ')+money(period.net_micro/1e6,true):t('Journal does not match the main result','Dziennik nie zgadza się z wynikiem głównym'));
    const empty=$('journal-empty');
    if(empty){empty.hidden=journal.length>0;empty.textContent=!board?t('no data','brak danych'):t('Confirmed zero closed PAPER trades in this period','Potwierdzone zero zamkniętych transakcji PAPER w tym okresie');}
    text('journal-count',!period||period.closed==null?t('no data','brak danych'):period.closed+' '+t('closed PAPER trades','zamkniętych transakcji PAPER')+(opens.length?' · '+opens.length+' '+t('open','otwarte'):''));
    text('journal-scope',t('Closed copies are the main number. Open copies are listed and are not in that sum.','Zamknięte kopie są liczbą główną. Otwarte kopie są na liście i nie wchodzą do tej sumy.'));
  }
}
let lastViewSig='',lastMitchSig='',fetchError='';
function holdScroll(){const el=document.scrollingElement||document.documentElement;return el?el.scrollTop:0;}
function restoreScroll(y){const apply=()=>{const el=document.scrollingElement||document.documentElement;if(el)el.scrollTop=y;if(document.body)document.body.scrollTop=y;};apply();requestAnimationFrame(apply);}
function viewSig(s){
  const board=paperBoardOf(s)||{};
  const period=board.periods&&board.periods[paperPeriod];
  const m=s.mitch_copy||{};
  const bank=s.profit_bank||m.profit_bank||{};
  return JSON.stringify([
    location.hash,paperPeriod,lang,journalBook,journalFilter,historyPage,connected,fetchError,
    period&&period.net_micro,period&&period.closed,board.open&&board.open.count,
    (period&&period.wallets||[]).map(w=>[w.wallet,w.net_micro,w.closed,w.copying]),
    m.closed_today_micro,m.closed_all_micro,m.open_count,m.journal,
    (m.wallets||[]).map(w=>[w.wallet,w.net_micro,w.paused,w.reserved_micro,w.copies]),
    bank.reserved_micro,bank.mitch_reserved_micro,bank.copy_reserved_micro
  ]);
}
function profitBankOf(s){return (s&&s.profit_bank)||(s&&s.mitch_copy&&s.mitch_copy.profit_bank)||{};}
function fillProfitBank(s){
  const bank=profitBankOf(s);
  for(const id of ['profit-bank-tile','mitch-bank']){
    const el=$(id);if(!el)continue;
    el.replaceChildren();
    const card=node('article',undefined,'strategy-card wallet-tile bank-card'+(Number(bank.reserved_micro)>0?' profit':''));
    card.append(node('div','Rezerwa zysku'+(bank.live?' · LIVE':' · PAPER'),'metric-label'));
    card.append(node('div',bank.reserved_micro==null?missing():money(Number(bank.reserved_micro)/1e6),'bank-amount'));
    const L=bank.ledgers||{};
    const grid=node('div',undefined,'bank-grid');
    for(const [name,l] of [['Mitch',L.mitch_accounts],['Portfele',L.wallet_copy_accounts]]){
      if(!l)continue;
      const box=node('div',undefined,'bank-ledger');
      const gap=(l.peak_micro||0)-(l.realized_micro||0);
      box.append(node('b',name+': '+money((l.reserved_micro||0)/1e6)));
      box.append(node('span','wynik '+money((l.realized_micro||0)/1e6,true)+' · szczyt '+money((l.peak_micro||0)/1e6,true)));
      box.append(node('span',gap>0?'do nowego szczytu brakuje '+money(gap/1e6):'na szczycie — każdy nowy plus dodaje 40%'));
      grid.append(box);
    }
    card.append(grid);
    card.append(node('p','Jak to działa: gdy wynik księgi bije swój rekord, 40% tej nadwyżki idzie do rezerwy i już tam zostaje. Wygrana, która tylko odrabia wcześniejszą stratę, nic nie dodaje. Na LIVE rezerwa będzie przenoszona na osobny portfel, z którego się nie handluje.','bank-note'));
    el.append(card);
  }
}
function render(){const scrollY=holdScroll();const s=state||blank();try{renderOpsBar(s);renderOverview(s);const sig=viewSig(s);if(sig===lastViewSig){restoreScroll(scrollY);return;}lastViewSig=sig;syncAssetUI(s);renderOpsBar(s);renderWalletPanel(s);const a=ownStrategies(s.accounts).find(x=>x.id===selected)||ownStrategies(s.accounts)[0]||{id:'',name:'',cash:null,pnl:null,trades:0,settled:0,wins:0,curve:[],initial:null};const live=connected&&!preview;const versionElement=$('service-version');if(versionElement)versionElement.textContent=serviceVersionLabel(s.worker,live,preview,Date.now()/1000);const age=Date.now()/1000-(s.worker.heartbeat||0);const healthy=live&&age<30&&s.worker.status==='RECORDING';text('status-text',preview?t('DESIGN PREVIEW','PODGLĄD PROJEKTU'):healthy?t('RECORDING','ZBIERANIE DANYCH'):live?t('SERVICE DEGRADED','SYSTEM WYMAGA UWAGI'):t('NOT CONNECTED','NIEPOŁĄCZONY'));text('status-detail',preview?t('Synthetic examples · excluded from research','Dane przykładowe · poza badaniem'):healthy?t('Collector connected. Strategy checks remain independent.','Kolektor połączony. Strategie osobno sprawdzają dane.'):live?t('Entries wait for valid data and service recovery.','Wejścia czekają na poprawne dane i działający system.'):t('The dashboard is ready. The 24/7 service is not connected.','Dashboard jest gotowy. Usługa 24/7 nie jest podłączona.'));$('status-dot').style.background=healthy?'var(--teal)':'var(--amber)';$('demo-banner').hidden=!preview;text('demo-banner',t('DESIGN PREVIEW — synthetic data, not trading results.','PODGLĄD PROJEKTU — dane sztuczne, to nie są wyniki handlu.'));text('pnl',a.settled?money(a.pnl,true):t('No settlements','Brak rozliczeń'));$('pnl').style.fontSize=a.settled?'':'1.35rem';$('pnl').className='metric-value '+(a.pnl>0?'positive':a.pnl<0?'negative':'');text('balance',money(a.cash));const selectedStatus=$('selected-account-status');if(selectedStatus){const last=(s.decisions||[]).find(d=>d.strategy===a.id);selectedStatus.textContent=(a.name||a.id)+' · '+a.trades+' '+t('trades','transakcji')+' · '+(last?reason(last.reason):t('No recorded decision','Brak zapisanej decyzji'))+(connected?'':' · '+t('Connection unavailable; last received data','Brak połączenia; ostatnio odebrane dane'));}text('capital-note',t('Research account · virtual ','Konto badawcze · wirtualne ')+money(a.initial??500));text('win-rate',a.settled?`${(100*a.wins/a.settled).toFixed(1)}%`:'—');text('trade-count',`${a.settled} ${t('settled trades','rozliczonych transakcji')}`);text('observations',s.observations==null?'—':s.observations.toLocaleString());text('labels',`${t('Official outcomes','Oficjalne wyniki')}: ${s.labels??'—'}`);chart(a.curve||[]);text('curve-period',a.curve?.length?`${formatTime(a.curve[0].ts)} — ${formatTime(a.curve.at(-1).ts)} · Stockholm`:t('No performance history','Brak historii wyników'));const ask=side=>{const book=s.market.books?.[side];return book?.asks?.length?`${(100*Math.min(...book.asks.map(x=>Number(x[0])))).toFixed(1)}¢`:'—';};text('up-ask',ask('Up'));text('down-ask',ask('Down'));text('reference-label',s.market.rule_kind==='TWAP60'?'Chainlink TWAP 60 s':t('Reference price','Cena referencyjna'));text('reference-price',money(s.reference?.price));text('opening-price',money(s.market.opening));const d=s.decisions.find(x=>x.strategy===selected);text('decision-reason',d?reason(d.reason):t('Awaiting verified data','Oczekiwanie na zweryfikowane dane'));
const cards=$('strategy-cards');if(cards)cards.replaceChildren();if(cards){const visibleAccounts=sortAccounts(ownStrategies(s.accounts));const books=bookParts(s.accounts);const totalPnl=books.strategy;const bar=node('div',undefined,'card-layout-bar');const autoBtn=node('button',t('Green on top','Zielone u góry'),'small-button'+(cardLayout==='auto'?' on':''));const manBtn=node('button',t('My order · drag','Mój układ · przeciągnij'),'small-button'+(cardLayout==='manual'?' on':''));autoBtn.type=manBtn.type='button';autoBtn.onclick=()=>{cardLayout='auto';localStorage.setItem('btc-lab-card-layout','auto');render();};manBtn.onclick=()=>{cardLayout='manual';if(!cardOrder.length)cardOrder=visibleAccounts.map(a=>a.id);localStorage.setItem('btc-lab-card-layout','manual');localStorage.setItem('btc-lab-card-order',JSON.stringify(cardOrder));render();};bar.append(autoBtn,manBtn);const totalBox=node('div',undefined,'total-pnl');totalBox.append(node('span',t('5–15 min strategies','Strategie 5–15 min')),node('strong',money(totalPnl,true),totalPnl>=0?'positive':'negative'),node('small',t('From the start of each strategy account. Copied wallets stay on Portfele.','Od początku każdego konta strategii. Kopiowane portfele zostają w Portfelach.')),node('small',`${t('Updated','Odświeżono')}: ${formatTime(s.generated_at)}`));cards.append(bar,totalBox);visibleAccounts.forEach((account,i)=>{const pnlClass=cardToneClass(account);const card=node('article',undefined,'strategy-card'+pnlClass+(account.id===selected?' selected':''));card.dataset.strategy=account.id;card.draggable=cardLayout==='manual';if(cardLayout==='manual'){card.addEventListener('dragstart',ev=>{ev.dataTransfer.setData('text/plain',account.id);card.classList.add('dragging');});card.addEventListener('dragend',()=>card.classList.remove('dragging'));card.addEventListener('dragover',ev=>ev.preventDefault());card.addEventListener('drop',ev=>{ev.preventDefault();const from=ev.dataTransfer.getData('text/plain');if(!from||from===account.id)return;const ids=visibleAccounts.map(a=>a.id);const a=ids.indexOf(from),b=ids.indexOf(account.id);if(a<0||b<0)return;ids.splice(a,1);ids.splice(b,0,from);cardOrder=ids;localStorage.setItem('btc-lab-card-order',JSON.stringify(cardOrder));render();});}const top=node('div',undefined,'strategy-top');top.append(node('span',`0${i+1} / ${asset} 15M`,'strategy-number'),node('span',cardKind(account),'chip'));card.append(top,node('h3',cardTitle(account)),node('p',cardBlurb(account)));const stats=node('div',undefined,'strategy-stats');const pairs=account.id.startsWith('copy-')?copyStatPairs(account):[[money(account.pnl,true),'P&L'],[String(account.trades),t('Paper trades','Transakcje testowe')]];for(const [v,label]of pairs){const box=node('div');box.append(node('strong',v),node('small',label));stats.append(box);}card.append(stats);if(account.id.startsWith('copy-')){for(const line of copyWatchLines(account))card.append(node('p',line,'watch-line'));}const pauses=s.strategy_pauses||{};if(Object.prototype.hasOwnProperty.call(pauses,account.id)){const paused=!!pauses[account.id];const btn=node('button',paused?t('Turn entries on','Włącz nowe zakłady'):t('Turn entries off','Wyłącz nowe zakłady'),'small-button strategy-toggle');btn.type='button';btn.onclick=async ev=>{ev.stopPropagation();try{const res=await fetch('./api/strategy-pause',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:account.id,paused:!paused,asset})});if(!res.ok)throw Error('pause');}catch(e){btn.textContent=t('Could not save','Nie zapisano');return;}refresh();};card.append(btn);if(paused)card.append(node('p',t('New entries are off. Open tickets still settle.','Nowe zakłady są wyłączone. Otwarte bilety nadal się rozliczają.')));}if(account.current_block)card.append(node('p',reason(account.current_block)));if(account.entry_capacity_usd!=null)card.append(node('p',`${t('Available next-entry budget including fees','Dostępna kwota kolejnego wejścia z opłatami')}: ${money(account.entry_capacity_usd)} · ${t('Market minimum still applies','Obowiązuje minimum rynku')}`));if(account.losses_7d!=null)card.append(node('p',`${t('Today net','Dzisiaj netto')}: ${money(account.today_pnl,true)} · ${t('7-day gross losses','Straty brutto 7 dni')}: ${money(account.losses_7d)} / ${money(account.week_limit)} · ${t('Next entry loss is also reserved','Limit uwzględnia też możliwą stratę nowego wejścia')}`));cards.append(card);});}
text('journal-filter-label',t('Journal strategy','Strategia w dzienniku'));text('journal-all',t('All strategies','Wszystkie strategie'));const bookSelect=$('journal-book');if(bookSelect){const bookLabel=$('journal-book-label');if(bookLabel)bookLabel.textContent=t('Journal book','Księga dziennika');if(bookSelect.dataset.ready!==lang){bookSelect.replaceChildren();for(const [value,label] of [['paper',t('PAPER accounts','Konta PAPER')],['policy',t('Policy observation','Obserwacja polityki')],['independent',t('Independent tickets','Niezależne bilety')]]){const o=node('option',label);o.value=value;bookSelect.append(o);}bookSelect.dataset.ready=lang;}bookSelect.value=journalBook;}const journalTrades=renderHistory(s);if($('journal-empty'))$('journal-empty').hidden=!!journalTrades.length;text('journal-scope',journalBook==='policy'?t('Policy observation only. Not the PAPER account.','Tylko obserwacja polityki. To nie konto PAPER.'):journalBook==='independent'?t('Independent hold-to-settlement tickets only. Not a PAPER profit and not a promotion.','Tylko niezależne bilety trzymane do rozstrzygnięcia. To nie zysk konta PAPER i nie awans.'):journalFilter==='all'?t('PAPER account fills only. Observation and independent tickets are separate views.','Tylko wypełnienia kont PAPER. Obserwacja i niezależne bilety są osobnymi widokami.'):`${journalFilter} · ${t('filtered from latest 100 service records; full day in Export report','filtr ostatnich 100 wpisów serwera; pełny dzień w Pobierz raport')}`);text('journal-count',`${journalTrades.length} ${t('recent trades','ostatnich transakcji')}`);text('collector-health',preview?'PREVIEW':healthy?'CONNECTED':live?'DEGRADED':'OFFLINE');text('model-health',isEth()?t('NOT USED','NIE JEST UŻYWANY'):s.model.status);text('training-count',isEth()?t('Separate ETH experiment','Osobny eksperyment ETH'):`${s.model.samples||0} / 200`);$('training-progress').hidden=isEth();$('training-progress').value=Math.min(200,s.model.samples||0);const events=$('events');if(events)events.replaceChildren();if(events){for(const error of (s.worker.errors||[])){const row=node('div',undefined,'event');row.append(node('span',error.stage),node('b',error.detail||error.error));events.append(row);}if(s.worker.reference_error){events.append(node('p',s.worker.reference_error,'muted'));}s.decisions.slice(0,6).forEach(d=>{const row=node('div',undefined,'event');row.append(node('time',formatTime(d.ts)),node('span',d.strategy),node('b',reason(d.reason)));events.append(row);});if(!s.decisions.length)events.append(node('p',t('No decisions recorded. Waiting for the worker.','Brak zapisanych decyzji. Oczekiwanie na silnik.'),'muted'));}text('updated',preview?t('Preview · not connected to a market','Podgląd · bez połączenia z rynkiem'):connected?`${t('Last response','Ostatnia odpowiedź')}: ${formatTime(s.generated_at)} · Stockholm`:t('No service connected','Usługa nie jest podłączona'));tick();installHelp();renderPaperBoard(s);fillProfitBank(s);renderMitch(s);}catch(error){fetchError=String(error&&error.message||error||'render').slice(0,80);}finally{restoreScroll(scrollY);}}
function tick(){text('clock',new Date().toLocaleTimeString('en-GB',{timeZone:'Europe/Stockholm'})+' · Stockholm');const now=Date.now()/1000;const remaining=state?.market?.end?Math.max(0,Math.floor(state.market.end-now)):null;text('countdown',remaining==null?'—:—':`${String(Math.floor(remaining/60)).padStart(2,'0')}:${String(remaining%60).padStart(2,'0')}`);const age=state?.reference?.source_ts?Math.max(0,now-state.reference.source_ts):null;text('reference-age',age==null?'—':`${age.toFixed(1)}s`);text('reference-health',preview?'PREVIEW':connected&&age!=null&&age<=5?'FRESH':'WAITING');}
let refreshBusy=false;
async function refresh(){
  if(preview||refreshBusy)return;
  refreshBusy=true;
  const requested=location.hash==='#strategie'?asset:'BTC';
  try{
    if(isEth()&&location.hostname.endsWith('github.io'))throw Error('ETH requires private backend');
    const endpoint=location.hostname.endsWith('github.io')?'./state.json':'./api/state?asset='+requested;
    const opts={cache:'no-store',credentials:'same-origin'};
    if(typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function')opts.signal=AbortSignal.timeout(25000);
    const res=await fetch(endpoint,opts);
    if(!res.ok)throw Error('HTTP '+res.status);
    const data=await res.json();
    if(data.demo===true||data.mode!=='PAPER'||!Array.isArray(data.accounts)||!Array.isArray(data.decisions)||!Array.isArray(data.trades)||(requested==='ETH'&&data.asset!=='ETH'))throw Error('invalid schema');
    if(requested!==asset||preview)return;
    state=data;connected=true;fetchError='';
  }catch(error){
    if(requested!==asset||preview)return;
    fetchError=String(error&&error.message||error||'offline').slice(0,80);
    if(!state)connected=false;
  }finally{refreshBusy=false;}
  render();
}

const guideEntries = [["start", "How to read this dashboard", "Jak czytać dashboard", "This is paper trading: simulated trades on market data. Review data quality after 24 hours; trades may appear earlier or may not occur. A day is not evidence of profitability. Each strategy has its own virtual account.", "To handel testowy: symulowane transakcje na danych rynkowych. Po 24 godzinach oceniamy jakość danych; transakcje mogą pojawić się wcześniej lub nie wystąpić. Doba nie dowodzi rentowności. Każda strategia ma osobne konto wirtualne."], ["status", "Recording and service status", "Zbieranie danych i stan usługi", "RECORDING means the collector reports activity, not that a strategy can trade. DEGRADED means a service or data check failed. NOT CONNECTED means the dashboard cannot fetch service state. A working screen alone is not proof of working strategies.", "RECORDING oznacza aktywność kolektora, a nie gotowość strategii do transakcji. DEGRADED oznacza problem usługi lub danych. NOT CONNECTED oznacza brak dostępu dashboardu do stanu usługi. Sam działający ekran nie potwierdza działania strategii."], ["pnl", "Realised paper P&L", "Zrealizowany wynik testowy", "Profit or loss from closed or officially resolved simulated positions, after entry cost and execution fees, before infrastructure costs. An open position is not realised profit. Positive P&L is not a promise of future returns.", "Zysk lub strata ze sprzedanych lub oficjalnie rozstrzygniętych pozycji testowych, po koszcie wejścia i opłatach, przed kosztami infrastruktury. Otwarta pozycja nie jest zrealizowanym zyskiem. Dodatni wynik nie gwarantuje kolejnych zysków."], ["cash", "Available paper cash", "Dostępna gotówka testowa", "Each strategy starts with virtual $500. Cash committed to positions is unavailable. After resolution, simulated redemption releases proceeds separately. This is not your Kraken balance and the accounts do not share capital.", "Każda strategia zaczyna od wirtualnych 500 USD. Środki zajęte przez pozycje są niedostępne. Po rozstrzygnięciu wpływy uwalnia osobne symulowane odebranie wypłaty. To nie jest saldo Kraken; strategie nie współdzielą kapitału."], ["winrate", "Settled win rate", "Skuteczność rozliczonych transakcji", "Profitable closed positions divided by all closed positions, after both fees. A high win rate can still lose money when a loss is larger than several wins. A dash means there are no settled trades.", "Liczba zyskownych zamkniętych pozycji podzielona przez wszystkie zamknięte pozycje, po obu prowizjach. Wysoka skuteczność może nadal oznaczać stratę, jeśli jedna przegrana przewyższa kilka wygranych. Kreska oznacza brak rozliczonych transakcji."], ["observations", "Observations and official outcomes", "Obserwacje i oficjalne wyniki", "Observations are recorded data events, not trades or independent training examples. Official outcomes label markets after resolution. Thousands of observations can correspond to very few completed 15-minute windows.", "Obserwacje to zapisane zdarzenia danych, nie transakcje ani niezależne przykłady treningowe. Oficjalne wyniki oznaczają rozstrzygnięte rynki. Tysiące obserwacji mogą dotyczyć zaledwie kilku zakończonych okien 15-minutowych."], ["chart", "Chart and strategy selector", "Wykres i wybór strategii", "The selector changes the account shown in the main performance metrics and chart. Strategy cards remain separate and the journal may include all strategies. The current chart needs at least two result points to draw a curve.", "Selektor zmienia konto prezentowane w głównych metrykach i na wykresie. Karty strategii pozostają osobne, a dziennik może obejmować wszystkie strategie. Obecny wykres potrzebuje co najmniej dwóch punktów wynikowych do narysowania krzywej."], ["window", "Current window and countdown", "Bieżące okno i odliczanie", "The market covers a 15-minute interval. The timer measures time until that interval ends, not time until a trade or official payout. Official settlement may arrive later.", "Rynek obejmuje przedział 15 minut. Zegar pokazuje czas do końca tego przedziału, a nie do transakcji czy oficjalnej wypłaty. Rozstrzygnięcie może nadejść później."], ["quotes", "UP / DOWN prices", "Ceny UP / DOWN", "These are the best displayed asks per share, in cents: 67¢ means $0.67, not $67. A winning share pays $1; a losing share pays $0. Costs include fees. The two asks can total more than 100¢; that difference is not itself the trading fee.", "To najlepsze widoczne oferty sprzedaży udziału, w centach: 67¢ oznacza 0,67 USD, a nie 67 USD. Wygrany udział wypłaca 1 USD, przegrany 0 USD. Dochodzą opłaty. Suma obu cen może przekraczać 100¢; ta różnica sama w sobie nie jest prowizją."], ["reference", "Chainlink TWAP 60 s", "Chainlink TWAP 60 s", "The supported market uses the specified Chainlink 60-second time-weighted price stream. It is not an exchange spot quote or an average over the entire 15-minute market. The feed must match the market rule.", "Obsługiwany rynek korzysta ze wskazanego strumienia Chainlink ze średnią ceny ważoną czasem z 60 sekund. To nie cena spot giełdy ani średnia z całego rynku 15-minutowego. Źródło musi odpowiadać regule rynku."], ["opening", "Opening reference", "Referencja otwarcia", "The reference at the market start is the comparison threshold. Starting the collector mid-window may leave it unavailable. The strategy skips that window instead of substituting a later price.", "Referencja z początku rynku jest progiem porównania. Uruchomienie kolektora w środku okna może oznaczać jej brak. Strategia pomija takie okno zamiast podmieniać cenę na późniejszą."], ["age", "Reference age and freshness", "Wiek i aktualność referencji", "Age is elapsed time since the source timestamp, not since the page was opened. Current checks require a reference no older than 5 seconds and an order book no older than 3 seconds. The page fetches state about every 10 seconds, so displayed age also reflects refresh timing.", "Wiek to czas od znacznika czasu źródła, a nie od otwarcia strony. Obecne kontrole wymagają referencji nie starszej niż 5 sekund oraz arkusza zleceń nie starszego niż 3 sekundy. Strona pobiera stan co około 10 sekund, więc widoczny wiek zależy też od momentu odświeżenia."], ["decisions", "Why there is no trade", "Dlaczego nie ma transakcji", "OUTSIDE_MODEL_HORIZON: outside the value model entry time. OUTSIDE_ENTRY_WINDOW: outside a baseline entry time. MODEL_COLLECTING: insufficient labelled data. OPENING_REFERENCE_MISSING: no start reference. RULE_UNVERIFIED: unsupported rule. REFERENCE_STALE / BOOK_STALE: stale data. NO_NET_EDGE: no estimated advantage after costs. NO_FULL_FILL: insufficient eligible liquidity. RISK_LIMIT: risk budget blocks entry. FILLED: a simulated fill, not a live order. Other error details appear in the decision log.", "OUTSIDE_MODEL_HORIZON: poza czasem wejścia modelu wartości. OUTSIDE_ENTRY_WINDOW: poza czasem wejścia strategii bazowej. MODEL_COLLECTING: za mało danych z wynikami. OPENING_REFERENCE_MISSING: brak referencji otwarcia. RULE_UNVERIFIED: nieobsługiwana reguła. REFERENCE_STALE / BOOK_STALE: nieaktualne dane. NO_NET_EDGE: brak szacowanej przewagi po kosztach. NO_FULL_FILL: za mała dostępna płynność. RISK_LIMIT: limit ryzyka blokuje wejście. FILLED: wykonanie symulowane, nie rzeczywiste zlecenie. Pozostałe szczegóły błędów są w dzienniku decyzji."], ["value", "Reference-aware value", "Wartość z referencją", "A research candidate compares an estimated probability with the executable price and costs. Its entry horizon is 115–125 seconds before market end. It first needs 200 eligible officially labelled windows. A candidate status is a model check, not proof of profitable trading.", "Kandydat badawczy porównuje szacowane prawdopodobieństwo z ceną wykonania i kosztami. Horyzont wejścia to 115–125 sekund przed końcem rynku. Najpierw potrzebuje 200 poprawnych okien z oficjalnym wynikiem. Status kandydata oznacza kontrolę modelu, a nie dowód zyskownego handlu."], ["late", "Late direction", "Późny kierunek", "A baseline inspired by Damian: follows the direction relative to the opening reference late in the market. It checks more than 30 and at most 300 seconds remaining, a minimum $50 distance and an ask in the 80–95.5¢ range. Data, execution and risk checks still apply.", "Strategia bazowa inspirowana Damianem: podąża za kierunkiem względem referencji otwarcia pod koniec rynku. Sprawdza ponad 30 i maksymalnie 300 sekund do końca, odległość co najmniej 50 USD i cenę 80–95,5¢. Nadal obowiązują kontrole danych, wykonania i ryzyka."], ["early", "Early direction", "Wczesny kierunek", "A baseline inspired by Mitch: tests an earlier directional entry. It checks more than 600 and at most 780 seconds remaining, a minimum $50 distance and an ask in the 60–64¢ range. This is a separately tested adaptation, not a claim to reproduce Mitch’s results.", "Strategia bazowa inspirowana Mitchem: testuje wcześniejsze wejście kierunkowe. Sprawdza ponad 600 i maksymalnie 780 sekund do końca, odległość co najmniej 50 USD i cenę 60–64¢. To osobno testowana adaptacja, nie deklaracja odtworzenia wyników Mitcha."], ["journal", "Trade journal: time, strategy, side, status", "Dziennik: czas, strategia, strona, status", "Time is shown in Stockholm time. Strategy identifies the virtual account; side is Up or Down. CLOSED is a full simulated sale before settlement; OPEN is an unsettled position; RESOLVED means its outcome is known; REDEEMED means simulated proceeds have been released. A market ending alone does not establish an official outcome.", "Czas jest wyświetlany dla Sztokholmu. Strategia wskazuje konto wirtualne, a strona to Up lub Down. CLOSED to pełna symulowana sprzedaż przed rozstrzygnięciem; OPEN to nierozliczona pozycja; RESOLVED oznacza znany wynik; REDEEMED oznacza uwolnienie symulowanej wypłaty. Sam koniec okna nie ustanawia oficjalnego wyniku."], ["fees", "Cost, fees and simulated execution", "Koszt, opłaty i symulacja wykonania", "Cost + fees is the simulated debit. A displayed quote is not a guaranteed fill. The simulator applies a delay, depth haircut, price limits, minimum size and full-fill requirement. Fee calculations remain a simulation and must be reconciled with exchange rules before live trading.", "Koszt + opłaty to obciążenie w symulacji. Widoczna cena nie gwarantuje wykonania. Symulator stosuje opóźnienie, ogranicza dostępną głębokość, sprawdza limity cen, minimalną wielkość i pełne wykonanie. Naliczanie opłat jest symulacją i wymaga uzgodnienia z regułami giełdy przed handlem rzeczywistym."], ["model", "Model and 200 labelled windows", "Model i 200 okien z wynikami", "The model uses eligible windows matching its feature schema, not every raw observation. 200 consecutive 15-minute windows take at least 50 hours, plus settlement time; missing data extends this. The current split is 140 training / 60 validation. Better probability accuracy does not automatically mean positive net returns.", "Model używa poprawnych okien zgodnych ze schematem cech, nie każdej obserwacji. 200 kolejnych okien 15-minutowych to minimum 50 godzin plus czas rozstrzygnięcia; braki danych wydłużają ten czas. Obecny podział to 140 okien treningowych i 60 walidacyjnych. Lepsza trafność prawdopodobieństw nie oznacza automatycznie zysku po kosztach."], ["risk", "Paper-only and risk limits", "Tryb testowy i limity ryzyka", "Real-money orders are disabled. Virtual accounts enforce exposure and loss budgets; a skipped trade can be the correct result. No daily profit is guaranteed. The $500 research account is not an instruction to deposit $500.", "Zlecenia za prawdziwe pieniądze są wyłączone. Konta wirtualne przestrzegają limitów ekspozycji i strat; pominięcie transakcji może być prawidłowym wynikiem. Nie ma gwarancji codziennego zysku. Konto badawcze 500 USD nie jest poleceniem wpłaty 500 USD."], ["operations", "24/7 target and infrastructure allowance", "Cel 24/7 i budżet infrastruktury", "The Mac collector needs the computer powered, awake, online and logged in. A locked screen is fine. “24/7 target” is not confirmation of continuous availability or assistant monitoring. €15/month is a planning allowance, not a charge or subscription.", "Kolektor na Macu wymaga zasilania, braku uśpienia, internetu i zalogowanego konta. Ekran może być zablokowany. „Cel 24/7” nie potwierdza ciągłej dostępności ani monitorowania przez asystenta. 15 EUR miesięcznie to założony budżet, nie naliczona opłata ani abonament."], ["export", "Report export and last response", "Eksport raportu i ostatnia odpowiedź", "Export fetches a fresh server report for the previous completed Stockholm day, or the selected past date. Includes daily and lifetime results, all daily trades, skip counts and freshness. Offline/preview export is blocked. Repeated exports overlap; do not sum lifetime totals. Last response is the dashboard fetch time, not the timestamp of every market observation.", "Eksport pobiera świeży raport z serwera za poprzedni zakończony dzień w Sztokholmie lub wybraną datę. Zawiera wyniki dzienne i łączne, transakcje dnia, przyczyny pominięć i aktualność. Eksport offline i podglądu jest zablokowany. Nie sumuj wyników łącznych z kolejnych plików. Ostatnia odpowiedź dotyczy pobrania stanu, a nie czasu każdej obserwacji rynku."]];
guideEntries.push(['mid','BTC 3–7 experiment','Eksperyment BTC 3–7',
'PAPER hypothesis, not a copy of Mitch’s undisclosed model. Buys from 180 through 420 elapsed seconds at 50–80 cents with persistent 30-second direction, volatility-scaled distance >=1 and spread <=3 cents. Full sale attempts before 600 seconds: net +10% target, net -20% stop, or time exit from 590 seconds. These are unvalidated research thresholds, not guaranteed fills or profit. Unfilled inventory remains exposed until official resolution. Each strategy retains its own virtual capital and loss limits.',
'Hipoteza PAPER, nie kopia nieujawnionego modelu Mitcha. Zakupy od 180 do 420 sekund od otwarcia po 50–80 centów; kierunek utrzymany 30 sekund, odległość skalowana zmiennością >=1 i spread <=3 centy. Próby pełnej sprzedaży przed 600 sekundą: cel +10% netto, stop -20% netto lub wyjście czasowe od 590 sekundy. To niezweryfikowane progi badawcze, nie gwarancja wykonania ani zysku. Niesprzedana pozycja pozostaje narażona na stratę do oficjalnego rozstrzygnięcia. Każda strategia zachowuje własny kapitał wirtualny i limity strat.']);
guideEntries.push(['eth','ETH PAPER experiment','Eksperyment ETH PAPER','ETH uses a separate database, virtual $500 account and eth-mid-window-v1 strategy. Entries at 3–7 minutes, asks 50–80 cents, 30-second directional persistence, volatility-scaled distance >=1 and spread <=3 cents. Net +10%/-20% or time-based exit attempts before minute 10; unfilled positions await official settlement. Own Chainlink ETH/USD TWAP 60s boundary and order books, no BTC-trained model or $50 BTC threshold. Same dimensionless baseline rules are a comparison hypothesis, not evidence they suit ETH. BTC and ETH can lose together. Reports and balances must not be combined as a single $100 portfolio.','ETH ma osobną bazę, konto wirtualne 500 USD i strategię eth-mid-window-v1. Wejścia w 3–7 minucie, ceny 50–80 centów, kierunek utrzymany 30 sekund, odległość skalowana zmiennością >=1 i spread do 3 centów. Próby wyjścia przy +10%/-20% netto lub limicie czasu przed 10 minutą; niesprzedane pozycje czekają na oficjalny wynik. Własne dane Chainlink ETH/USD TWAP 60 s i arkusze ofert; bez modelu BTC i progu 50 USD dla BTC. Wspólne reguły względne są hipotezą porównawczą, nie dowodem ich skuteczności na ETH. BTC i ETH mogą tracić razem. Tych kont nie sumujemy jako jednego portfela 100 USD.']);
guideEntries.push(['value-surface','Value Surface PAPER','Value Surface PAPER','Separate virtual100USD account per asset. Uses prior officially resolved markets at matching minute and signed volatility bucket; minimum50 prior windows per cell. Not a calibrated or proven edge. Buys after250ms to5s on a new book with50% depth and both costs; max1USD all-in, shrinking after losses. Full sales when net executable bids exceed estimated upper hold value; otherwise official settlement. Minimum order can block entries. No guaranteed stop. Wallet observations do not yet feed this model.','Osobne wirtualne100USD dla każdego aktywa. Wykorzystuje wcześniejsze oficjalnie rozstrzygnięte rynki z podobnej minuty i odległości skalowanej zmiennością; minimum50 okien w grupie. Przewaga niepotwierdzona. Zakup po250ms–5s na nowym arkuszu z połową głębokości; koszt z opłatą do1USD, malejący po stratach. Pełna sprzedaż, gdy dostępna wartość netto przekracza górne oszacowanie wartości trzymania; inaczej oficjalne rozliczenie. Minimum zlecenia może blokować zakupy. Brak gwarantowanego stopu. Dane portfeli nie zasilają jeszcze tego modelu.']);
strings.pl.guide='Przewodnik';
function helpLink(key){const a=node('a',t('What is this?','Co to jest?'),'help-link');a.href='#guide-'+key;const e=guideEntries.find(x=>x[0]===key);a.setAttribute('aria-label',a.textContent+' '+e[lang==='pl'?2:1]);return a;}
function installHelp(){
 const mapping={'journal-strategy':'journal',pnl:'pnl',balance:'cash','win-rate':'winrate',observations:'observations',labels:'observations',account:'chart',countdown:'window','up-ask':'quotes','down-ask':'quotes','reference-label':'reference','opening-price':'opening','reference-age':'age','decision-reason':'decisions','status-detail':'status','collector-health':'status','reference-health':'age','model-health':'model','training-count':'model',export:'export',updated:'export'};
 for(const [id,key] of Object.entries(mapping)){const el=$(id);if(!el)continue;const next=el.nextElementSibling;if(!next?.classList.contains('help-link'))el.after(helpLink(key));}
 for(const [selector,key] of [['[data-i18n="performance"]','chart'],['[data-i18n="currentWindow"]','window'],['[data-i18n="paperOnly"]','risk'],['[data-i18n="systemHealth"]','operations'],['[data-i18n="liveOrders"]','risk'],['[data-i18n="costPlan"]','operations'],['[data-i18n="decisionLog"]','decisions'],['[data-i18n="strategyComparison"]','start']]){const el=document.querySelector(selector);if(el&&!el.nextElementSibling?.classList.contains('help-link'))el.after(helpLink(key));}
 document.querySelectorAll('thead th').forEach((el,i)=>{if(el.closest('#wynik')||el.closest('#dziennik'))return;if(!el.nextElementSibling?.classList.contains('help-link')&&!el.querySelector('.help-link'))el.append(helpLink(i===3?'fees':i===5?'pnl':'journal'));});
 document.querySelectorAll('.strategy-card').forEach(el=>{if(el.querySelector('.help-link'))return;const id=el.dataset.strategy||'';const key=id.startsWith('copy-')?'start':id==='eth-mid-window-v1'?'eth':id==='value-surface-paper-v1'?'value-surface':id==='late-v1'?'late':id==='early-v1'?'early':(id==='mid-window-v1'||id==='mid-window-v2')?'mid':'value';el.append(helpLink(key));});
 document.querySelectorAll('.help-link').forEach(a=>{const key=a.hash.slice(7),e=guideEntries.find(x=>x[0]===key);a.textContent=t('What is this?','Co to jest?');if(e)a.setAttribute('aria-label',a.textContent+' '+e[lang==='pl'?2:1]);});
}
function renderGuide(){
 text('guide-title',t('Your dashboard, explained.','Twój dashboard — wyjaśnienia.'));
 text('guide-intro',t('Understand the numbers, the strategies and why the system sometimes waits.','Poznaj liczby, strategie i powody, dla których system czasem czeka.'));
 text('guide-back',t('← Back to dashboard','← Wróć do dashboardu'));
 $('guide-toc').replaceChildren();$('guide-content').replaceChildren();
 for(const e of guideEntries){const title=e[lang==='pl'?2:1];const link=node('a',title);link.href='#guide-'+e[0];$('guide-toc').append(link);const card=node('article',undefined,'panel guide-card');card.id='guide-'+e[0];card.tabIndex=-1;card.append(node('h2',title),node('p',e[lang==='pl'?4:3]));const back=node('a',t('↑ Guide contents','↑ Spis treści'));back.href='#guide';card.append(back);$('guide-content').append(card);}
}
function routeGuide(){
  const names={przeglad:'Przegląd',wynik:'Portfele',mitch:'Mitch',dziennik:'Historia',obserwacje:'Odkrywanie',strategie:'Archiwum 5–15 min',diagnostyka:'System',guide:'Opis'};
  const alias={overview:'przeglad',activity:'dziennik',wallets:'obserwacje',kandydaci:'obserwacje',strategies:'strategie',operations:'diagnostyka'};
  let name=(location.hash||'#przeglad').slice(1);
  if(name.startsWith('guide'))name='guide';
  name=alias[name]||name;
  if(!names[name])name='przeglad';
  for(const id of Object.keys(names)){const el=$(id);if(el)el.hidden=id!==name;}
  text('tab-name',names[name]);
  document.querySelectorAll('.nav-item').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+name));
  document.querySelectorAll('.project-tabs a').forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+name));
}
window.addEventListener('hashchange',routeGuide);

function syncAssetUI(s){
 $('asset').value=asset;const own=ownStrategies(s.accounts);const ids=own.map(a=>a.id);if(!ids.includes(selected))selected=ids[0]||selected;if(journalFilter!=='all'&&!ids.includes(journalFilter))journalFilter='all';
 for(const id of ['account','journal-strategy']){const el=$(id),wanted=id==='account'?selected:journalFilter;el.replaceChildren();if(id==='journal-strategy'){const o=node('option',t('All 5–15 min strategies','Wszystkie strategie 5–15 min'));o.value='all';o.id='journal-all';el.append(o);}for(const a of own){const o=node('option',a.name||a.id);o.value=a.id;el.append(o);}el.value=wanted;}
 text('asset-label',t('Market','Rynek'));text('asset-build',asset+' · 15 MIN');text('asset-heading',(isEth()?'ETHEREUM':'BITCOIN')+' / POLYMARKET');if($('asset-window'))text('asset-window',asset);
 $('asset-note').hidden=!isEth();text('asset-note',t('ETH · separate PAPER experiment · virtual $500 · no BTC-trained model. New history starts after installation. Missing opening reference: wait for a fully observed window.','ETH · osobny eksperyment PAPER · wirtualne 500 USD · bez modelu BTC. Historia zaczyna się po instalacji. Brak referencji otwarcia: oczekiwanie na pełne zaobserwowane okno.'));
}
$('asset').onchange=e=>{asset=e.target.value;localStorage.setItem('btc-lab-asset',asset);selected=isEth()?'eth-mid-window-v1':'value-v1';journalFilter='all';state=null;connected=false;translate();refresh();};
$('journal-strategy').onchange=e=>{journalFilter=e.target.value;render();};const journalBookSelect=$('journal-book');if(journalBookSelect)journalBookSelect.onchange=e=>{journalBook=e.target.value;localStorage.setItem('btc-lab-journal-book',journalBook);render();};
$('language').onclick=()=>{lang=lang==='en'?'pl':'en';localStorage.setItem('btc-lab-language',lang);translate();};$('account').onchange=e=>{selected=e.target.value;render();};$('export').onclick=async()=>{return exportDaily();};document.querySelectorAll('.nav-item').forEach(a=>a.onclick=()=>{document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));a.classList.add('active');});bindHistory();translate();refresh();setInterval(refresh,2000);setInterval(tick,1000);


async function exportDaily(){
 const button=$('export');button.disabled=true;
 try{
  if(preview||location.hostname.endsWith('github.io'))throw Error(t('Open the connected private dashboard to export a real report.','Otwórz połączony prywatny dashboard, aby pobrać prawdziwy raport.'));
  const date=$('report-date').value;const requested=asset;
  const res=await fetch('./api/report?asset='+requested+(date?'&date='+encodeURIComponent(date):''),{cache:'no-store',signal:AbortSignal.timeout(30000)});
  if(!res.ok)throw Error(t('Report unavailable. No cached file was downloaded.','Raport niedostępny. Nie pobrano starego pliku z pamięci.'));
  const data=await res.json();
  if(data.schema!=='btc-daily-report-v2'||(requested==='ETH'&&data.asset!=='ETH'))throw Error(t('Update the Mac backend for daily reports.','Zaktualizuj backend na Macu, aby pobierać raporty dzienne.'));
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=node('a');a.href=url;a.download=`${requested.toLowerCase()}-lab-${data.period.date}-Stockholm.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  text('export-status',`${t('Downloaded day','Pobrano dzień')}: ${data.period.date} · ${data.worker_fresh_at_export?data.worker.status:t('WARNING: stale worker','UWAGA: nieaktualny stan procesu')}`);
 }catch(e){text('export-status',e.message);}finally{button.disabled=false;}
}



function renderWalletPanel(s){
 const obs=$('wallet-content');const cand=$('candidate-content');if(!obs)return;obs.replaceChildren();if(cand)cand.replaceChildren();
 let box=obs;
 const now=Date.now()/1000;
 const stamp=x=>x?new Date(x*1000).toLocaleString(lang==='pl'?'pl-PL':'en-GB',{timeZone:'Europe/Stockholm'}):t('not available','brak danych');
 const add=(tag,content)=>{const e=node(tag,content);e.style.overflowWrap='anywhere';box.append(e);return e;};
 if(preview){add('p',t('Wallet data is unavailable in synthetic preview.','Dane portfeli nie są dostępne w sztucznym podglądzie.'));return;}
 add('p',t('Hypothetical observation only. These figures are not the PAPER copy result.','Tylko obserwacja hipotetyczna. Te liczby nie są wynikiem kopiowania PAPER.'));
 const cp=s.wallet_copy_execution||{};
 if(s.wallet_copy_error?.error)add('p',s.wallet_copy_error.error);
 for(const a of cp.accounts||[]){
  if(!(a.watch))continue;
  add('h3',(a.name||a.wallet||'').slice(-40));
  if(typeof copyWatchLines==='function'){for(const line of copyWatchLines(a))add('p',line);}
 }
 add('h3',t('Skipped copies — hypothetical hold result','Pominięte kopie — hipotetyczny wynik do rozliczenia'));
 const sr=cp.skip_review;
 add('p',t('Target polling every second; actual delay includes API indexing and network. Shadow tickets are independent, not account profit or source-sale replication.','Cel: odczyt co sekundę; rzeczywiste opóźnienie obejmuje API i sieć. Hipotetyczne zakupy są niezależne — to nie wynik konta ani kopia sprzedaży źródła.'));
 if(!sr)add('p',t('No skip-review data from this service version.','Ta wersja usługi nie przekazała ocen pominięć.'));
 else {
  add('p',t('Recorded skips: ','Zapisane pominięcia: ')+sr.total+(sr.truncated?t(' · latest 100 only',' · tylko ostatnie 100'):''));
  for(const r of (sr.recent||[]).slice(0,10))add('p',stamp(r.decision_at)+' · '+String(r.source_event?.proxyWallet||'')+' · '+String(r.reason||'')+' · '+t('Detection delay: ','Opóźnienie odczytu: ')+String(r.detection_delay??'—')+'s · '+String(r.shadow?.status||r.status||'')+' · '+(r.counterfactual_pnl==null?t('No calculable PnL','Brak policzalnego wyniku'):money(r.counterfactual_pnl)));
 }
 const wallets=s.wallet_observer||[];
 if(!wallets.length)add('p',t('No observer data from this backend. Check the service version and report.','Ten backend nie przekazał danych obserwatora. Sprawdź wersję usługi i raport.'));
 for(const w of wallets){
  add('h3',(w.label?w.label+' · ':'')+w.wallet);const age=now-Number(w.checked_at||0);const fresh=connected&&age>=0&&age<=90;
  add('p',(fresh?(w.status||'UNKNOWN'):t('STALE / no current confirmation','NIEAKTUALNE / brak bieżącego potwierdzenia'))+' · '+t('Last check: ','Ostatnia próba: ')+stamp(w.checked_at));
  add('p',t('Recorded events: ','Zapisane zdarzenia: ')+(w.unique_fingerprints??t('unknown','brak danych'))+' · '+t('Last event: ','Ostatnie zdarzenie: ')+stamp(w.last_event_at));
  if(w.error)add('p',w.error);
 }
 add('h3',t('Recent observed activity','Ostatnie zaobserwowane zdarzenia'));
 const events=s.wallet_activity_recent||[];
 if(!events.length)add('p',t('No events in the available observation history. This is not a zero-profit claim.','Brak zdarzeń w dostępnej historii obserwacji. To nie oznacza zerowego zysku portfela.'));
 for(const e of events.slice(0,10))add('p',stamp(e.source_ts)+' · '+String(e.wallet)+' · '+String(e.side||e.type||'')+' · '+String(e.title||'')+' · '+t('price ','cena ')+String(e.price??'—')+' · '+t('shares ','udziały ')+String(e.size??'—'));
 const d=s.wallet_discovery||{};
 if(cand)box=cand;
 add('h3',t('New wallet candidates — hourly search','Nowi kandydaci — wyszukiwanie co godzinę'));
 const da=now-Number(d.last_success_at||0);
 add('p',(d.status||t('NOT STARTED','NIEURUCHOMIONE'))+((!connected||da<0||da>3900)?' · '+t('no fresh successful scan','brak świeżego udanego skanowania'):'')+' · '+t('Last success: ','Ostatni sukces: ')+stamp(d.last_success_at));
 if(d.error)add('p',d.error);
 add('p',t('These are leads for copied wallets, not the 5–15 min strategies. They come from the live trade tape and the CRYPTO month board. The board is not a score. The copier still drops a signal older than 90s when we see it. That is not a requirement of 90s left in the market. Passing the 20–70¢ band is not a result after fees. A wallet is watched first. PAPER_TEST opens only after our own hypothetical copies clear the roster rules. Live orders stay off.','To są kandydaci do kopiowanych portfeli, nie strategie 5–15 min. Biorą się z bieżącej taśmy i z miesięcznej tablicy CRYPTO. Tablica nie jest oceną. Kopiarka nadal odrzuca sygnał starszy niż 90 s w chwili wykrycia. To nie jest wymóg 90 s do końca rynku. Przejście pasma 20–70¢ to nie wynik po opłatach. Portfel najpierw jest obserwowany. PAPER_TEST startuje dopiero, gdy nasze hipotetyczne kopie przejdą reguły listy. Zlecenia na żywo są wyłączone.'));
 if(!(d.candidates||[]).length)add('p',d.status==='SCAN_OK'?t('No candidates met this screen.','Żaden kandydat nie spełnił tego filtra.'):t('Candidate results are unavailable.','Brak wyników wyszukiwania kandydatów.'));
 for(const c of d.candidates||[]){
  const share=c.our_share_30d==null?'—':Math.round(c.our_share_30d*100)+'%';
  const ours=c.our_trades_30d==null?'—':c.our_trades_30d;
  const why=(c.reject_reasons||[]).join(', ');
  add('p',c.wallet+' · '+(c.source||'leaderboard')+' · '+t('month: ','miesiąc: ')+money(c.month_reported_pnl)+' · '+t('trades the copier saw: ','transakcje widziane przez kopiarkę: ')+ours+' · '+t('share: ','udział: ')+share+' · '+(c.status||'SHORTLIST_30D')+(c.decision?' · '+c.decision:'')+(why?' · '+why:''));
 }
 for(const a of (d.recent_audit||[]).slice(-8))add('p',stamp(a.ts)+' · '+String(a.action||'')+' · '+String(a.wallet||'').slice(-8)+' · '+String(a.reason||''));
 add('h3',t('Probability experiment','Eksperyment prawdopodobieństwa'));
 const v=s.value_surface_execution||{};const r=s.opportunity_research||{};
 add('p',v.status?reason(v.status):t('No execution state received','Nie otrzymano stanu wykonania'));
 add('p',t('Research state: ','Stan badania: ')+(r.status||t('not available','brak danych'))+' · '+t('Updated: ','Aktualizacja: ')+stamp(r.updated_at));
}
function bindHistory(){
  const fields=[['history-wallet','btc-lab-history-wallet'],['history-date','btc-lab-history-date'],['history-kind','btc-lab-history-kind']];
  for(const [id,key] of fields){
    const el=$(id);if(!el||el.dataset.bound)continue;
    el.dataset.bound='1';
    el.value=localStorage.getItem(key)|| (id==='history-kind'?'all':'');
    el.addEventListener('input',()=>{historyPage=0;localStorage.setItem(key,el.value);localStorage.setItem('btc-lab-history-page','0');render();});
    el.addEventListener('change',()=>{historyPage=0;localStorage.setItem(key,el.value);localStorage.setItem('btc-lab-history-page','0');render();});
  }
  const prev=$('history-prev'),next=$('history-next');
  if(prev&&!prev.dataset.bound){prev.dataset.bound='1';prev.onclick=()=>{historyPage=Math.max(0,historyPage-1);localStorage.setItem('btc-lab-history-page',String(historyPage));render();};}
  if(next&&!next.dataset.bound){next.dataset.bound='1';next.onclick=()=>{historyPage+=1;localStorage.setItem('btc-lab-history-page',String(historyPage));render();};}
}
function renderHistory(s){
  const all=filterJournal(openCopyTrades(s).concat(journalRows(s)),journalFilter);
  const walletQ=(($('history-wallet')||{}).value||'').trim().toLowerCase();
  const dateQ=($('history-date')||{}).value||'';
  const kind=($('history-kind')||{}).value||'all';
  const filtered=all.filter(tr=>{
    const label=String(tr.strategy||'').toLowerCase();
    if(walletQ&&!label.includes(walletQ))return false;
    if(dateQ){
      const day=new Date((tr.opened||0)*1000).toLocaleDateString('en-CA',{timeZone:'Europe/Stockholm'});
      if(day!==dateQ)return false;
    }
    const status=String(tr.status||'');
    const side=String(tr.side||'').toUpperCase();
    if(kind==='open'&&status!=='OPEN'&&status!=='RESOLVED')return false;
    if(kind==='closed'&&(status==='OPEN'||status==='RESOLVED'))return false;
    if(kind==='buy'&&side==='SELL')return false;
    if(kind==='sell'&&side!=='SELL')return false;
    return true;
  });
  const pages=Math.max(1,Math.ceil(filtered.length/25));
  if(historyPage>=pages)historyPage=pages-1;
  if(historyPage<0)historyPage=0;
  const slice=filtered.slice(historyPage*25,historyPage*25+25);
  const rows=$('trades');
  if(rows){
    rows.replaceChildren();
    slice.forEach(tr=>{const row=node('tr');const pnl=journalPnl(tr);const costText=tr.hypothetical&&!tr.cost_known?missing():money((tr.cost+tr.fee+(tr.exit_fee||0))/1e6);[formatTime(tr.opened),journalLabel(tr,s.accounts),tr.side,costText,journalStatus(tr),pnl==null?missing():money(pnl,true)].forEach((v,i)=>row.append(node('td',v,i===5?(pnl>0?'positive':pnl<0?'negative':''):'')));rows.append(row);});
  }
  text('history-page',(historyPage+1)+' / '+pages+' · '+filtered.length);
  return filtered;
}
function renderOpsBar(s){
  const el=$('ops-status');if(!el)return;
  const now=Date.now()/1000;
  const beat=Number((s.worker||{}).heartbeat||0);
  const age=beat?now-beat:null;
  const generated=Number(s.generated_at||0);
  const genAge=generated?now-generated:null;
  const pageLate=!connected||genAge==null||genAge>20;
  const collectorLate=age==null||age>45;
  const ledgerBad=(s.wallet_copy_health||{}).status==='ledger_mismatch';
  const stale=pageLate||ledgerBad;
  const watch=s.service_watch||{};
  const clock=s.clock_status||{};
  const mitch=s.mitch_copy||{};
  const copyAt=(s.wallet_copy_execution||{}).updated_at;
  const copyAge=copyAt?now-Number(copyAt):null;
  const mitchAge=mitch.updated_at?now-Number(mitch.updated_at):null;
  const moneyMs=v=>v==null?'brak danych':(Number(v).toFixed(0)+' ms');
  const sec=v=>v==null?'brak danych':(Number(v).toFixed(0)+' s');
  const copyStep=s.wallet_copy_progress||{};
  const mitchStep=s.mitch_progress||{};
  const copyStepAge=copyStep.at?now-Number(copyStep.at):null;
  const mitchStepAge=mitchStep.at?now-Number(mitchStep.at):null;
  const lat=((s.wallet_copy_execution||{}).latency)||{};
  const exec=lat.total||lat.exec||{};
  const parts=[
    ledgerBad?ledgerLine(s):(pageLate?('AWARIA — ekran nie dostał świeżej odpowiedzi'+(fetchError?' · '+fetchError:'')):(collectorLate?'kolektor późny':'kolektor świeży')),
    'sprawdzenie kolektora '+sec(age),
    'ostatnia publikacja wyników: '+(copyAge==null?'brak publikacji':(Number(copyAge).toFixed(0)+' s temu')),
    'kolejka kopii '+(copyStep.queue==null?'brak danych':String(copyStep.queue))+' · ostatnie sprawdzenie kopiarki '+sec(copyStepAge),
    'opóźnienie wykonania '+(exec.median_ms==null?'brak pomiaru':(exec.median_ms+' ms, n='+(exec.n==null?'brak':exec.n))),
    'Mitch publikacja '+(mitchAge==null?'brak publikacji':(Number(mitchAge).toFixed(0)+' s temu'))+' · kolejka '+(mitchStep.queue==null?'brak':String(mitchStep.queue))+' · krok '+sec(mitchStepAge),
    chainLine(s),
    tunnelLine(s),
    'nadzór '+(watch.status||'brak danych')+(watch.noted&&watch.noted.length?' · '+watch.noted.join(','):'')+(watch.problems&&watch.problems.length?' · restart: '+watch.problems.join(','):'')+(watch.launch_wait&&watch.launch_wait.reason?' · '+watch.launch_wait.reason:''),
    'restarty '+(watch.restarts_in_window==null?'brak danych':String(watch.restarts_in_window)),
    'zegar '+(clock.status||'brak pomiaru')+' · '+moneyMs(clock.offset_ms)+' · '+(clock.source||'brak źródła')+' · '+(clock.checked_at?formatTime(clock.checked_at):'brak sprawdzenia')+' · niepewność '+moneyMs(clock.uncertainty_ms)
  ];
  el.textContent=parts.join(' · ');
  el.className='ops-status '+(stale?'bad':'ok');
  document.body.classList.toggle('data-stale',stale);
}
function chainLine(s){
  const c=s.chain_status||{};
  if(c.connected==null&&c.events_matched==null)return 'łańcuch: brak statusu';
  return 'łańcuch '+(c.connected?'połączony':'rozłączony')+' · dopasowane '+(c.events_matched==null?'brak':String(c.events_matched))+' · porzucone '+(c.events_dropped==null?'brak':String(c.events_dropped))+' · paragon '+(c.bridged==null?'brak':String(c.bridged));
}
function tunnelLine(s){
  const t=s.tunnel_status||{};
  if(t.edge_connected==null)return 'tunel: brak statusu';
  return 'tunel '+(t.edge_connected?'krawędź jest':'krawędź nie jest')+' · HTTP '+(t.http_status==null?'brak':String(t.http_status))+(t.reason?' · '+t.reason:'');
}
function openWalletDetail(s,account,row,openCount){
  const box=$('wallet-detail');if(!box)return;
  box.hidden=false;
  const wallet=account.wallet||String(account.id).replace(/^copy-/,'');
  const net=row&&row.net_micro!=null?money(row.net_micro/1e6,true):missing();
  box.replaceChildren();
  const head=node('div',undefined,'panel-heading');
  const title=node('div');
  title.append(node('h2',String(wallet).slice(-8)),node('p',wallet));
  const close=node('button','Zamknij','small-button');
  close.type='button';
  close.onclick=()=>{localStorage.removeItem('btc-lab-open-wallet');box.hidden=true;box.replaceChildren();};
  head.append(title,close);
  box.append(head,node('p','Stan: '+(account.roster_state||'brak danych')+' · wynik okresu: '+net+' · otwarte kopie: '+(openCount||0)+(row&&row.pause_reason?' · '+row.pause_reason:'')));
}
function mitchSignature(m){
  if(!m)return 'none';
  return JSON.stringify({
    t:m.closed_today_micro,a:m.closed_all_micro,o:m.open_count,h:m.health,
    j:m.journal,r:m.recent,b:m.book,
    w:(m.wallets||[]).map(x=>[x.wallet,x.net_micro,x.paused,x.copies,x.open,x.reserved_micro,x.tradable_micro])
  });
}
const MITCH_REASON={
  MITCH_BUY:['Kupiono','ok'],MITCH_ADD:['Dokupiono','ok'],MITCH_SELL:['Sprzedano','ok'],
  LATE_BUY_NOT_COPIED:['Za późno (ponad 1 s)','skip'],PRICE_WORSE_THAN_10C:['Cena gorsza o ponad 10¢','skip'],
  MITCH_PAUSED:['Portfel na pauzie','stop'],GLOBAL_STOP:['STOP z Telegrama','stop'],WINDOW_LIMIT:['Limit okna wyczerpany','skip'],
  NO_LIQUIDITY:['Za mała płynność','skip'],NO_ASK:['Brak ofert sprzedaży','skip'],BOOK_STALE:['Arkusz nieaktualny','skip'],
  BOOK_WAIT_TOO_LONG:['Arkusz przyszedł za wolno','skip'],MITCH_NEED_CHAIN:['Brak jego ceny z giełdy','skip'],
  SOURCE_TIME_UNKNOWN:['Nieznany czas jego transakcji','skip'],MARKET_CLOSED:['Rynek zamknięty','skip'],
  FEE_UNCONFIRMED:['Opłata niepotwierdzona','skip'],SOURCE_PROPORTION_UNKNOWN:['Nieznana część sprzedaży','skip'],
  LATE_SELL_RECONCILED:['Spóźniona sprzedaż, wg bieżącego arkusza','ok'],MITCH_LEDGER_HOLD:['Księga się nie zgadza','stop']
};
function mitchMetric(label,value,note,cls){
  const card=node('article',undefined,'metric');
  card.append(node('div',label,'metric-label'));
  card.append(node('div',value,'metric-value small'+(cls?' '+cls:'')));
  if(note)card.append(node('div',note,'metric-note'));
  return card;
}
function renderMitchFast(m){
  const banner=$('stop-banner');if(banner)banner.hidden=!(m&&m.stop_active);
  const box=$('mitch-fast');if(!box)return;
  const f=m&&m.fast;const st=m&&m.stint;
  const rows=m&&Array.isArray(m.wallets)?m.wallets:[];
  box.replaceChildren();
  const age=f&&f.at?Date.now()/1000-f.at:null;
  const live=f&&f.prints>0&&age!=null&&age<60;
  box.append(mitchMetric('Szybka ścieżka',!f?missing():live?'działa':'czeka',
    f?(f.prints+' printów · '+f.resolved+' odczytanych · '+f.missed+' chybionych'):'Brak statusu.',live?'positive':f?'':'negative'));
  box.append(mitchMetric('Odczyt jego transakcji',f&&f.resolve_median_ms!=null?Math.round(f.resolve_median_ms)+' ms':missing(),
    f&&f.resolve_p90_ms!=null?'mediana · p90 '+Math.round(f.resolve_p90_ms)+' ms · cel: decyzja poniżej 1 s':'Od printu CLOB do odczytu transakcji.'));
  const copies=rows.reduce((n,r)=>n+(r.period_copies||0),0);
  const net=rows.reduce((n,r)=>n+(r.period_net_micro||0),0);
  box.append(mitchMetric('Okres testu: wynik',rows.length?money(net/1e6,true):missing(),
    copies+' kopii · '+rows.reduce((n,r)=>n+(r.period_closed||0),0)+' zamkniętych',net>0?'positive':net<0?'negative':''));
  box.append(mitchMetric('Okres testu od',st&&st.at?formatTime(st.at):missing(),
    'Pauza liczy tylko ten okres. Wynik od startu zostaje poniżej.'));
  renderMitchDecisions(m);
}
function renderMitchDecisions(m){
  const body=$('mitch-decisions');if(!body)return;
  const rows=m&&Array.isArray(m.period_events)?m.period_events:[];
  const labels={};for(const w of (m&&m.wallets)||[])labels[w.wallet]=w.label;
  const sig=JSON.stringify(rows.map(r=>[r.at,r.reason]));
  if(body.dataset.sig===sig)return;
  body.dataset.sig=sig;
  body.replaceChildren();
  const empty=$('mitch-decisions-empty');if(empty)empty.hidden=!!rows.length;
  const count=$('mitch-decisions-count');
  if(count){const r=m&&m.period_reasons||{};const bought=(r.MITCH_BUY||0)+(r.MITCH_ADD||0);count.textContent=bought+' kopii · '+Object.values(r).reduce((a,b)=>a+b,0)+' decyzji';}
  for(const row of rows){
    const [text,kind]=MITCH_REASON[row.reason]||[row.reason,'skip'];
    const tr=document.createElement('tr');
    tr.append(node('td',formatTime(row.at)));
    tr.append(node('td',labels[row.wallet]||String(row.wallet||'').slice(-8)));
    tr.append(node('td',text,'decision-'+kind));
    tr.append(node('td',row.side==='BUY'?'kupno':row.side==='SELL'?'sprzedaż':(row.side||'—')));
    tr.append(node('td',row.market||'—'));
    tr.append(node('td',row.total_ms==null?'—':Math.round(row.total_ms)+' ms'));
    body.append(tr);
  }
}

function ovRow(label,value,ok){
  const row=node('div',undefined,'health-row');
  const left=node('span');
  const dot=node('span',undefined,'status-dot');dot.style.background=ok===true?'var(--teal)':ok===false?'var(--red)':'var(--amber)';dot.style.marginRight='9px';
  left.append(dot,document.createTextNode(label));
  row.append(left,node('b',value));
  return row;
}
function renderOverview(s){
  const net=$('overview-net');if(!net)return;
  const now=Date.now()/1000;
  const m=s.mitch_copy||{};const w=(s.wallet_copy_execution||{}).board||{};const p=w.periods||{};
  const usd=v=>v==null?missing():money(v/1e6,true);
  const cls=v=>v>0?'positive':v<0?'negative':'';
  const rows=Array.isArray(m.wallets)?m.wallets:[];
  const periodNet=rows.reduce((n,r)=>n+(r.period_net_micro||0),0);
  const own=typeof ownStrategies==='function'?ownStrategies(s.accounts||[]):[];
  const ownNet=own.reduce((n,a)=>n+(Number(a.pnl)||0),0);
  const bank=s.profit_bank||{};
  const sig=JSON.stringify([m.closed_all_micro,m.closed_today_micro,periodNet,p.today&&p.today.net_micro,p.all&&p.all.net_micro,ownNet.toFixed(2),bank.reserved_micro]);
  if(net.dataset.sig!==sig){
    net.dataset.sig=sig;net.replaceChildren();
    net.append(mitchMetric('Mitch · okres testu',usd(periodNet),'dziś '+usd(m.closed_today_micro)+' · od startu '+usd(m.closed_all_micro),cls(periodNet)));
    const copyBuys=(s.wallet_copy_execution||{}).buys_enabled;
    net.append(mitchMetric('Portfele · od startu',usd(p.all&&p.all.net_micro),'dziś '+usd(p.today&&p.today.net_micro)+' · 7 dni '+usd(p.week&&p.week.net_micro)+(copyBuys===false?' · kupno wstrzymane':''),cls(p.all&&p.all.net_micro)));
    net.append(mitchMetric('Archiwum strategii',money(ownNet,true),'zatrzymane 9.10 · tylko rozliczenia',cls(ownNet)));
    net.append(mitchMetric('Rezerwa zysku',bank.reserved_micro==null?missing():money(bank.reserved_micro/1e6),'40% nowych szczytów księgi',''));
  }
  const ready=$('overview-ready');
  if(ready){
    ready.replaceChildren();
    const ev=(m.period_events||[]).filter(e=>(e.reason==='MITCH_BUY'||e.reason==='MITCH_ADD')&&e.total_ms!=null).map(e=>e.total_ms).sort((a,b)=>a-b);
    const med=ev.length?ev[Math.floor(ev.length/2)]:null;
    const copies=rows.reduce((n,r)=>n+(r.period_copies||0),0);
    const days=m.stint&&m.stint.at?(now-m.stint.at)/86400:0;
    const f=m.fast||{};
    const checks=[
      ['Kopia poniżej 1 s od jego transakcji',med==null?(f.resolve_median_ms!=null?'odczyt '+Math.round(f.resolve_median_ms)+' ms · czeka na kopie':'brak danych'):Math.round(med)+' ms (mediana)',med==null?null:med<1000],
      ['Co najmniej 100 kopii w okresie testu',copies+' / 100',copies>=100],
      ['Co najmniej 14 dni okresu testu',days.toFixed(1)+' / 14 dni',days>=14],
      ['Wynik okresu testu na plus po opłatach',usd(periodNet),copies?periodNet>0:null],
      ['Prawdziwe zlecenia zablokowane w kodzie',s.live_enabled?'NIE':'tak',!s.live_enabled],
      ['Własny portfel i wykonanie LIVE','jeszcze nie zbudowane',null],
    ];
    const done=checks.filter(c=>c[2]===true).length;
    text('overview-ready-count',done+' / '+checks.length);
    for(const [label,value,ok] of checks)ready.append(ovRow(label,value,ok));
  }
  const sys=$('overview-system');
  if(sys){
    sys.replaceChildren();
    const wk=s.worker||{};const hb=now-(wk.heartbeat||0);
    const f=m.fast||{};const fage=f.at?now-f.at:null;
    const tg=s.telegram_status||{};const clk=s.clock_status||{};const ch=s.chain_status||{};const tun=s.tunnel_status||{};
    sys.append(ovRow('Worker',(wk.status||'—')+' · heartbeat '+Math.round(hb)+' s',wk.status==='RECORDING'&&hb<30));
    sys.append(ovRow('Szybka ścieżka (CLOB → mempool)',f.prints?(f.resolved+'/'+f.prints+' · '+Math.round(f.resolve_median_ms||0)+' ms'):'czeka',f.prints>0&&fage!=null&&fage<90));
    sys.append(ovRow('Łańcuch Polygon',ch.connected?'połączony':'brak',!!ch.connected));
    sys.append(ovRow('Zegar',(clk.status||'—')+(clk.offset_ms!=null?' · '+Math.round(clk.offset_ms)+' ms':''),clk.status==='synced'));
    sys.append(ovRow('Telegram',tg.ok?'połączony':tg.configured?'brak odpowiedzi':'nie skonfigurowany',tg.ok?true:tg.configured?false:null));
    sys.append(ovRow('Tunel zdalny',tun.edge_connected?'połączony':tun.edge_connected===false?'rozłączony':'—',tun.edge_connected===true?true:tun.edge_connected===false?false:null));
    const rec=s.recorder_status||{};
    const recDays=rec.started_at?((now-rec.started_at)/86400).toFixed(1):null;
    sys.append(ovRow('Rejestrator danych (badania)',rec.ok==null?'nie działa':rec.ok?('zapis od '+recDays+' dni · '+(rec.bytes/1e9).toFixed(2)+' GB'):(rec.paused?'wstrzymany: mało miejsca':'brak danych: '+(rec.stale||[]).join(', ')),rec.ok==null?null:!!rec.ok));
    sys.append(ovRow('STOP z Telegrama',m.stop_active?'AKTYWNY':'nie',m.stop_active?false:true));
    sys.append(ovRow('Tryb','PAPER · LIVE wyłączone',!s.live_enabled));
  }
  const bankBox=$('overview-bank');
  if(bankBox){
    bankBox.replaceChildren();
    const L=bank.ledgers||{};
    const line=(name,l)=>{if(!l)return;const peak=l.peak_micro||0;const real=l.realized_micro||0;
      bankBox.append(ovRow(name,'rezerwa '+money((l.reserved_micro||0)/1e6)+' · wynik '+money(real/1e6,true)+' · szczyt '+money(peak/1e6,true)+(peak>real?' · do nowego szczytu brakuje '+money((peak-real)/1e6):''),real>=peak&&peak>0?true:null));};
    line('Mitch',L.mitch_accounts);line('Portfele',L.wallet_copy_accounts);
    const prev=[L.mitch_accounts,L.wallet_copy_accounts].reduce((n,l)=>n+((l&&l.previous_rule_reserved_micro)||0),0);
    if(prev){const note=node('p','Stara reguła (40% każdej wygranej, bez odejmowania strat) pokazywała '+money(prev/1e6)+'. Przeliczone 9.10 na nową regułę.','metric-note');note.style.margin='12px 22px';bankBox.append(note);}
  }
}

function renderMitch(s){
  const m=s.mitch_copy;
  renderMitchFast(m);
  const sig=mitchSignature(m);
  if(sig===lastMitchSig)return;
  lastMitchSig=sig;
  const note=$('mitch-miha-note');
  if(note){
    note.textContent=(m&&m.miha_5m&&m.miha_5m.note)||'Miha 5m nie jest kopiowany. 15m zostaje jak jest.';
  }
  const bookBox=$('mitch-book');
  if(bookBox){
    bookBox.replaceChildren();
    const book=m&&m.book;
    if(!book){
      bookBox.append(node('p','Brak jeszcze odczytu arkusza przy decyzji Mitcha. To nie jest ukryty bid.'));
    }else{
      const ask=book.has_ask?(book.best_ask+' · głębokość '+book.ask_depth):'brak ask';
      const bid=book.has_bid?(book.best_bid+' · głębokość '+book.bid_depth):'brak bid';
      bookBox.append(node('p',(book.slug||'brak rynku')+' · '+(book.side||'brak strony')+' · '+(book.copy_state||'brak stanu')));
      bookBox.append(node('p','Ask: '+ask+' · Bid: '+bid+(book.error?' · '+book.error:'')));
      if(book.seen_at)bookBox.append(node('p','Odczyt '+formatTime(book.seen_at)+' · token '+(book.token||'brak')));
    }
  }
  const root=$('mitch-metrics');if(!root)return;
  const show=v=>v==null||v===''?missing():(Number(v)===0?'0,00 USD · potwierdzone zero':money(Number(v)/1e6,true));
  root.replaceChildren();
  const cards=[
    ['Dzisiaj, zamknięte',m?show(m.closed_today_micro):missing()],
    ['Od startu, zamknięte',m?show(m.closed_all_micro):missing()],
    ['Otwarte, koszt',m&&m.open_cost_micro!=null?money(m.open_cost_micro/1e6):missing()],
    ['Otwarte, wycena',m&&m.open_mark_micro!=null?money(m.open_mark_micro/1e6,true):missing()]
  ];
  for(const [label,value] of cards){
    const card=node('article',undefined,'metric');
    card.append(node('div',label,'metric-label'),node('div',value,'metric-value'));
    root.append(card);
  }
  const tiles=$('mitch-wallets');
  if(tiles){
    tiles.replaceChildren();
    const rows=m&&Array.isArray(m.wallets)?m.wallets:[];
    if(!rows.length)tiles.append(node('p','Brak danych projektu Mitch. To nie jest zero.'));
    for(const row of rows){
      const net=row.net_micro;
      const card=node('article',undefined,'strategy-card wallet-tile'+(row.paused?' paused':'')+(net>0?' profit':net<0?' loss':''));
      card.append(node('h3',row.label||String(row.wallet||'').slice(-8)));
      const pnet=row.period_net_micro;
      card.append(node('p','Okres testu: '+(pnet==null?missing():money(pnet/1e6,true))+' · '+(row.period_copies||0)+' kopii, '+(row.period_closed||0)+' zamkniętych'));
      card.append(node('p','Od startu: '+(net==null?missing():money(net/1e6,true))));
      if(row.paused)card.append(node('p','ZAKUPY WSTRZYMANE: minus w okresie testu albo dziś. Sprzedaż i rozliczenie zostają. Nie zdejmuje się sama.'));
      const since=row.spent_since_start_micro==null?missing():money(row.spent_since_start_micro/1e6);
      const wins=Array.isArray(row.windows)?row.windows:[];
      const current=wins.find(item=>item.open);
      const currentText=current?(money(current.spent_micro/1e6)+' / '+money(current.limit_micro/1e6)+' w bieżącym oknie'):'brak otwartego okna';
      const breaks=row.window_limit_breaks==null?missing():String(row.window_limit_breaks);
      card.append(node('p','Kopie: '+(row.copies==null?missing():String(row.copies))+' · wydatki od startu: '+since+' · '+currentText+' · okna ponad limitem: '+breaks));
      const reserved=row.reserved_micro==null?missing():money(row.reserved_micro/1e6);
      const tradable=row.tradable_micro==null?missing():money(row.tradable_micro/1e6);
      card.append(node('p','Otwarte: '+(row.open==null?missing():String(row.open))+' · koszt '+(row.open_cost_micro==null?missing():money(row.open_cost_micro/1e6))+' · zarezerwowane '+reserved+' · do kolejnych transakcji '+tradable+(row.buy_hold?' · zakupy wstrzymane, księga się nie zgadza':'')));
      card.onclick=()=>{
        const detail=$('mitch-detail');
        if(!detail)return;
        detail.hidden=false;
        detail.replaceChildren(node('h2',row.label||''),node('p',row.wallet||''),node('p','Wynik zamknięty: '+(net==null?missing():money(net/1e6,true))),node('p',row.paused?'Zakupy wstrzymane.':'Zakupy tylko z jego transakcji na giełdzie, decyzja poniżej 1 s od niej.'));
      };
      tiles.append(card);
    }
  }
  const body=$('mitch-trades');
  const empty=$('mitch-trades-empty');
  if(body){
    body.replaceChildren();
    const journal=m&&Array.isArray(m.journal)?m.journal:[];
    if(empty)empty.hidden=!!journal.length;
    for(const row of journal){
      const tr=document.createElement('tr');
      const cells=[
        formatTime(row.at),
        String(row.wallet||'').slice(-8),
        row.slug||'brak rynku',
        row.source_price==null?'brak':String(row.source_price),
        row.copy_vwap==null?'brak':String(row.copy_vwap),
        row.status||'brak',
        row.pnl_micro==null?missing():money(Number(row.pnl_micro)/1e6,true)
      ];
      for(const value of cells)tr.append(node('td',value));
      body.append(tr);
    }
  }
  const extra=$('mitch-extra');
  if(!extra)return;
  extra.replaceChildren();
  if(!m){extra.append(node('p','Brak danych. Założenia i opóźnienia pojawią się po pierwszym zapisie projektu.'));return;}
  extra.append(node('p','Księga Mitcha: '+(m.health||'brak kontroli')+(m.breaks&&m.breaks.length?' · '+m.breaks.map(b=>String(b.wallet||'').slice(-8)+' różnica gotówki '+(b.cash_minus_capital_ledger)+', księgi '+(b.book_minus_capital_pnl)).join('; '):'')));
  extra.append(node('p','Zakup tylko z jego transakcji odczytanej z giełdy (mempool, paragon albo print), poniżej 1 s od niej. Lista publiczna nie jest ceną zakupu.'));
  extra.append(node('p','Oczekiwanie na potwierdzenie ceny: '+(m.awaiting_price==null?missing():String(m.awaiting_price))));
  const reasons=m.reasons||{};
  const reasonText=Object.keys(reasons).length?Object.entries(reasons).map(([k,v])=>k+' '+v).join(' · '):'brak decyzji';
  extra.append(node('p','Decyzje: '+reasonText));
  const late=m.late||{};
  extra.append(node('p','Spóźnione zakupy w okresie od startu kopiowania. Przed aktywacją: '+(late.before_activation==null?'brak':String(late.before_activation))+'. Nowe sygnały pominięte przez program: '+(late.after_activation_not_copied==null?'brak':String(late.after_activation_not_copied))+'. Bez znacznika czasu: '+(late.unstamped==null?'brak':String(late.unstamped))+'. Pominięcie nie jest utraconym zyskiem.'));
  extra.append(node('p','Wersja: '+(m.spec||missing())+' · kapitał PAPER: '+(m.capital_usd_per_wallet==null?missing():money(m.capital_usd_per_wallet))+' na portfel. '+String(m.capital_note||'')));
  extra.append(node('p',m.sum_matches?'Suma portfeli zgadza się z wynikiem projektu.':'Suma portfeli nie zgadza się z wynikiem projektu albo brakuje danych.'));
  for(const line of m.assumptions||[])extra.append(node('p',line));
  extra.append(node('p',m.grouping||''));
  const lat=m.latency||{};
  const pack=block=>!block||block.n==null?'brak danych':(block.n+' próbek, mediana '+(block.median_ms==null?'brak':block.median_ms+' ms')+', p95 '+(block.p95_ms==null?'brak':block.p95_ms+' ms')+', max '+(block.max_ms==null?'brak':block.max_ms+' ms')+', poniżej 1 s '+(block.under_1000_pct==null?'brak':block.under_1000_pct+'%'));
  extra.append(node('p','Wykonane kopie z zapisanym pomiarem: '+(lat.samples==null?missing():String(lat.samples))+' · bez zapisanego pomiaru: '+(lat.executed_without_timing==null?missing():String(lat.executed_without_timing))));
  extra.append(node('p','Opóźnienie wykrycia: '+pack(lat.detect)));
  extra.append(node('p','Kolejka lokalna: '+pack(lat.queue)));
  extra.append(node('p','Księga: '+pack(lat.book)));
  extra.append(node('p','Razem: '+pack(lat.total)+(lat.total_confirmed?' · pomiar potwierdzony.':' · pomiar całkowity niepotwierdzony. '+(lat.note||''))));
  const recent=m.recent||[];
  if(!recent.length)extra.append(node('p','Brak zapisanych zdarzeń. To nie jest zero kopii z rynku, tylko pusty dziennik od startu.'));
  for(const event of recent.slice(0,25)){
    const detail=event.detail||{};
    extra.append(node('p',formatTime(event.at)+' · '+String(event.wallet||'').slice(-8)+' · '+event.reason+' · źródło '+(detail.source_price||'brak')+' · kopia '+(detail.copy_vwap==null?'brak':detail.copy_vwap)));
  }
}

