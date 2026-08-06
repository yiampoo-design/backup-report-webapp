const token = new URLSearchParams(location.search).get("token") || "";
let csrfToken = "";
let webUsername = "";
const headers = {"Content-Type":"application/json", "X-App-Token":token};
const $ = id => document.getElementById(id);

async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{...headers, ...(csrfToken?{"X-CSRF-Token":csrfToken}:{}), ...(options.headers||{})}});
  const payload = await response.json();
  if (response.status === 401 && payload.login_required) {
    location.replace("/login");
    throw new Error("กรุณาเข้าสู่ระบบ");
  }
  if (!response.ok || payload.ok === false) throw new Error(payload.error || "เกิดข้อผิดพลาด");
  return payload;
}

async function loadSession() {
  if (token) {
    $("accountButton").hidden = true;
    $("logoutButton").hidden = true;
    return;
  }
  const session = await api("/api/session");
  csrfToken = session.csrf_token;
  webUsername = session.username;
  $("accountUsername").textContent = webUsername;
}

function closeAccount() {
  $("accountModal").hidden = true;
  $("passwordForm").reset();
  $("passwordError").textContent = "";
}

async function logout() {
  await api("/api/logout", {method:"POST", body:"{}"});
  location.replace("/login");
}

async function changePassword(event) {
  event.preventDefault();
  const button = $("changePasswordButton");
  const error = $("passwordError");
  error.textContent = "";
  const payload = {
    current_password: $("currentWebPassword").value,
    new_password: $("newWebPassword").value,
    confirm_password: $("confirmWebPassword").value,
  };
  if (payload.new_password !== payload.confirm_password) {
    error.textContent = "ยืนยันรหัสผ่านใหม่ไม่ตรงกัน";
    return;
  }
  button.disabled = true;
  try {
    await api("/api/change-password", {method:"POST", body:JSON.stringify(payload)});
    location.replace("/login");
  } catch (exc) {
    error.textContent = exc.message;
  } finally {
    button.disabled = false;
  }
}

function toast(message) {
  const node = $("toast"); node.textContent = message; node.classList.add("show");
  setTimeout(()=>node.classList.remove("show"), 3500);
}

function sitePayload(site) {
  const payload = {
    label: $(`${site}Label`).value.trim(),
    url: $(`${site}Url`).value.trim(),
    username: $(`${site}Username`).value.trim(),
    password: $(`${site}Password`).value,
    verify_ssl: $(`${site}Verify`).checked,
  };
  if (site === "sangfor") {
    payload.enabled = $("sangforEnabled").checked;
    payload.backup_path = $("sangforBackupPath").value.trim();
  }
  return payload;
}

function allSettings() {
  return {
    primary: sitePayload("primary"), remote: sitePayload("remote"), sangfor: sitePayload("sangfor"),
    report: {server_name:$("serverName").value.trim(), alert_days:Number($("alertDays").value||3)}
  };
}

function setStatus(site, text, kind="idle") {
  const node = $(`${site}Status`); node.textContent=text; node.className=`status ${kind}`;
}

function result(message, ok=true) {
  const node=$("resultPanel"); node.textContent=message; node.className=`result-panel ${ok?"success":"error"}`;
}

async function loadSettings() {
  const {settings:s}=await api("/api/settings");
  $("version").textContent=`v${s.app.version}`;
  for (const site of ["primary","remote","sangfor"]) {
    $(`${site}Label`).value=s[site].label; $(`${site}Url`).value=s[site].url;
    $(`${site}Username`).value=s[site].username; $(`${site}Verify`).checked=s[site].verify_ssl;
    $(`${site}Saved`).textContent=s[site].password_saved?"บันทึกรหัสผ่านแล้ว":"ยังไม่ได้บันทึกรหัสผ่าน";
  }
  $("sangforEnabled").checked=s.sangfor.enabled;
  $("sangforBackupPath").value=s.sangfor.backup_path;
  $("serverName").value=s.report.server_name; $("alertDays").value=s.report.alert_days;
}

async function saveSettings() {
  const button=$("saveSettings"); button.disabled=true;
  try {
    const {settings}=await api("/api/settings",{method:"POST",body:JSON.stringify(allSettings())});
    for (const site of ["primary","remote","sangfor"]) {
      $(`${site}Password`).value="";
      $(`${site}Saved`).textContent=settings[site].password_saved?"บันทึกรหัสผ่านแล้ว":"ยังไม่ได้บันทึกรหัสผ่าน";
    }
    toast("บันทึกการตั้งค่าแล้ว");
  } catch(e) { result(e.message,false); } finally { button.disabled=false; }
}

async function testSangfor() {
  const button=$("testSangfor"); button.disabled=true;
  setStatus("sangfor","กำลัง Login และ Capture","busy");
  $("sangforPreview").hidden=true;
  try {
    const response=await api("/api/test-sangfor",{method:"POST",body:JSON.stringify({sangfor:sitePayload("sangfor")})});
    setStatus("sangfor","Capture สำเร็จ","ok");
    $("sangforPreview").href=response.preview_url;
    $("sangforPreview").hidden=false;
    result(`ทดสอบ Sangfor สำเร็จ\nURL: ${response.url}\nภาพ: ${response.path}`);
  } catch(e) {
    setStatus("sangfor","Capture ไม่สำเร็จ","bad");
    result(e.message,false);
  } finally { button.disabled=false; }
}

async function testSites(sites) {
  sites.forEach(s=>setStatus(s,"กำลังเชื่อมต่อ","busy"));
  try {
    const payload={sites}; sites.forEach(s=>payload[s]=sitePayload(s));
    const response=await api("/api/test",{method:"POST",body:JSON.stringify(payload)});
    for (const site of sites) {
      const item=response.results[site];
      setStatus(site,item.ok?"เชื่อมต่อสำเร็จ":"เชื่อมต่อไม่สำเร็จ",item.ok?"ok":"bad");
    }
    const lines=Object.entries(response.results).map(([site,item])=>item.ok
      ? `${item.label}: OK\nAPI: ${item.available_apis.join(", ")}${item.security_warning?"\nคำเตือน: URL ยังเป็น HTTP":""}`
      : `${site}: ${item.error}`);
    result(lines.join("\n\n"),response.ok);
  } catch(e) { sites.forEach(s=>setStatus(s,"เชื่อมต่อไม่สำเร็จ","bad")); result(e.message,false); }
}

async function probe(site) {
  setStatus(site,"กำลังตรวจ API","busy");
  try {
    const response=await api("/api/probe",{method:"POST",body:JSON.stringify({section:site,[site]:sitePayload(site)})});
    setStatus(site,"ตรวจ API สำเร็จ","ok");
    result(`บันทึกผลตรวจแล้ว: ${response.file}\nพบ Method ที่ตอบกลับ: ${response.successful_calls.join(", ")||"ยังไม่พบ"}\nทดลองทั้งหมด ${response.attempted_calls} รายการ`);
  } catch(e) { setStatus(site,"ตรวจ API ไม่สำเร็จ","bad"); result(e.message,false); }
}

async function generateReport() {
  const button=$("generateReport"); button.disabled=true;
  setStatus("report","กำลังดึงข้อมูลจาก NAS","busy");
  result("กำลังอ่าน Active Backup และ Cloud Sync ผ่าน Web API แล้วสร้าง PDF...");
  try {
    const response=await api("/api/generate",{method:"POST",body:JSON.stringify(allSettings())});
    setStatus("report","สร้างรายงานสำเร็จ","ok");
    result(`สร้างรายงานสำเร็จ\nรายการ Active Backup: ${response.rows}\nสถานะ Check: ${response.check_count}\nCloud Sync connections: ${response.cloud_sync.connection_count}\nSangfor capture: ${response.sangfor.enabled?"แนบแล้ว":"ไม่ได้เปิดใช้"}\nไฟล์: ${response.path}`);
    window.open(`${response.url}?token=${encodeURIComponent(token)}`,"_blank");
    loadReportHistory();
  } catch(e) {
    setStatus("report","สร้างรายงานไม่สำเร็จ","bad"); result(e.message,false);
  } finally { button.disabled=false; }
}

function formatBytes(bytes) {
  if (bytes >= 1024*1024) return `${(bytes/(1024*1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${bytes} Bytes`;
}

async function loadReportHistory() {
  const list=$("reportHistory");
  list.replaceChildren(Object.assign(document.createElement("div"),{className:"history-empty",textContent:"กำลังโหลดประวัติ..."}));
  try {
    const response=await api("/api/reports");
    $("historySummary").textContent=`พบ ${response.reports.length} รายงานภายใน ${response.days} วัน`;
    list.replaceChildren();
    if (!response.reports.length) {
      list.append(Object.assign(document.createElement("div"),{className:"history-empty",textContent:"ยังไม่มีรายงานในช่วง 7 วันที่ผ่านมา"}));
      return;
    }
    for (const report of response.reports) {
      const item=document.createElement("div"); item.className="report-item";
      const meta=document.createElement("div"); meta.className="report-meta";
      const name=document.createElement("div"); name.className="report-name"; name.textContent=report.name;
      const detail=document.createElement("small");
      detail.textContent=`${new Date(report.modified).toLocaleString("th-TH")} • ${formatBytes(report.size)}`;
      meta.append(name,detail);
      const actions=document.createElement("div"); actions.className="report-actions";
      const open=document.createElement("a"); open.className="button secondary"; open.textContent="เปิด"; open.target="_blank";
      open.href=`/api/report/${encodeURIComponent(report.name)}?token=${encodeURIComponent(token)}`;
      const download=document.createElement("a"); download.className="button ghost"; download.textContent="ดาวน์โหลด";
      download.href=`/api/report/${encodeURIComponent(report.name)}?token=${encodeURIComponent(token)}&download=1`;
      actions.append(open,download); item.append(meta,actions); list.append(item);
    }
  } catch(e) {
    $("historySummary").textContent="";
    list.replaceChildren(Object.assign(document.createElement("div"),{className:"history-empty",textContent:e.message}));
  }
}

function selectTab(name) {
  document.querySelectorAll(".tab-button").forEach(button=>{
    const active=button.dataset.tab===name; button.classList.toggle("active",active); button.setAttribute("aria-selected",String(active));
  });
  $("tabCreate").hidden=name!=="create"; $("tabHistory").hidden=name!=="history";
  $("tabCreate").classList.toggle("active",name==="create"); $("tabHistory").classList.toggle("active",name==="history");
  if (name==="history") loadReportHistory();
}

document.querySelectorAll(".test-button").forEach(b=>b.addEventListener("click",()=>testSites([b.dataset.site])));
document.querySelectorAll(".probe-button").forEach(b=>b.addEventListener("click",()=>probe(b.dataset.site)));
$("saveSettings").addEventListener("click",saveSettings);
$("testAll").addEventListener("click",()=>testSites(["primary","remote"]));
$("generateReport").addEventListener("click",generateReport);
$("testSangfor").addEventListener("click",testSangfor);
document.querySelectorAll(".tab-button").forEach(button=>button.addEventListener("click",()=>selectTab(button.dataset.tab)));
$("refreshHistory").addEventListener("click",loadReportHistory);
$("openReports").addEventListener("click",async()=>{
  const response=await api("/api/open-reports",{method:"POST",body:"{}"});
  if(response.history) selectTab("history");
});
$("accountButton").addEventListener("click",()=>{$("accountModal").hidden=false; $("currentWebPassword").focus();});
$("logoutButton").addEventListener("click",logout);
document.querySelectorAll("[data-close-account]").forEach(node=>node.addEventListener("click",closeAccount));
$("passwordForm").addEventListener("submit",changePassword);
document.addEventListener("keydown",event=>{if(event.key==="Escape" && !$("accountModal").hidden) closeAccount();});

loadSession().then(loadSettings).catch(e=>result(e.message,false));
