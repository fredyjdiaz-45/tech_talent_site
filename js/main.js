// ─── CITY DATA ───
  const CITIES = [
    {id:"kc", city:"Kansas City", state:"Missouri",
     lede:"USDA's largest workforce hub outside DC. Headquarters of NRCS, FSA, and RMA — the agencies closest to producers. The crossroads where ag policy meets engineering execution.",
     meta:{"Tech Roles":"780+ open","COL Index":"92 (avg = 100)","Avg Commute":"23 min","Cohort":"Largest"},
     agencies:["NRCS","FSA","RMA","AMS","OCIO"]},
    {id:"stl", city:"St. Louis", state:"Missouri",
     lede:"Geospatial powerhouse. Home to a major USDA data engineering presence. If you work in maps, imagery, or pipelines — this is the room.",
     meta:{"Tech Roles":"240+ open","COL Index":"88","Specialty":"Geospatial / Data Eng","Cohort":"Mid-large"},
     agencies:["NASS","ERS","OCIO","FAS"]},
    {id:"fc", city:"Fort Collins", state:"Colorado",
     lede:"Where the science happens. Forest Service R&D, APHIS labs, and NRCS modeling teams. Mountains out the window. Trail access from the campus.",
     meta:{"Tech Roles":"180+ open","COL Index":"108","Specialty":"ML / Forest Tech","Cohort":"Mid"},
     agencies:["Forest Service","APHIS","ARS","NRCS"]},
    {id:"slc", city:"Salt Lake City", state:"Utah",
     lede:"Western lands operations and Forest Service tech. If your work touches public lands — the 193 million acres of forests and grasslands — this is the closest you'll get to it.",
     meta:{"Tech Roles":"120+ open","COL Index":"104","Specialty":"Public Lands / SRE","Cohort":"Mid"},
     agencies:["Forest Service","BLM-adjacent","OCIO"]},
    {id:"ind", city:"Indianapolis", state:"Indiana",
     lede:"USDA's data-center anchor and a fast-growing software hub. Corn, soy, and infrastructure modernization. Cost of living that lets a tech salary actually mean something.",
     meta:{"Tech Roles":"140+ open","COL Index":"85","Specialty":"Cloud / Platform Eng","Cohort":"Mid"},
     agencies:["FSA","OCIO","RMA"]},
    {id:"ral", city:"Raleigh", state:"North Carolina",
     lede:"Research Triangle's federal corner. Biotech, ag genomics, and the cyber security operations center. Strong university pipeline makes it the densest tech-talent corridor in our network.",
     meta:{"Tech Roles":"210+ open","COL Index":"98","Specialty":"Cyber / Bioinformatics","Cohort":"Large"},
     agencies:["APHIS","ARS","OCIO","Cyber Ops"]},
    {id:"dc", city:"Washington", state:"District of Columbia",
     lede:"Headquarters. Where technology meets policy, budget, and the Office of the CIO. The room where enterprise architecture, governance, and department-wide modernization get decided.",
     meta:{"Tech Roles":"320+ open","COL Index":"152","Specialty":"Policy / Enterprise Arch","Cohort":"Large"},
     agencies:["OCIO","OCFO","DEC","Cyber Ops"]}
  ];

  const tilesEl = document.getElementById("layoutTiles");
  tilesEl.innerHTML = CITIES.map(c => `
    <div class="tile">
      <div class="tile-photo" data-pat="${c.id}">
        <span class="placeholder-tag">Photo placeholder</span>
      </div>
      <div class="tile-body">
        <div class="state">${c.state}</div>
        <h3>${c.city}</h3>
      </div>
    </div>`).join("");

  function handleSignup(e){
    e.preventDefault();
    document.getElementById("signupForm").style.display = "none";
    document.querySelector(".signup-meta").style.display = "none";
    document.getElementById("signupSuccess").classList.add("on");
    return false;
  }
