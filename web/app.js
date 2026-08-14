const token = new URLSearchParams(location.search).get("token") || "";
let csrfToken = "";
let webUsername = "";
let taskListClipboardFile = null;
let taskListPreviewUrl = "";
const headers = {"Content-Type":"application/json", "X-App-Token":token};
const $ = id => document.getElementById(id);

async function api(path, options={}) {
  const {allowErrorPayload=false, ...fetchOptions} = options;
  const response = await fetch(path, {...fetchOptions, headers:{...headers, ...(csrfToken?{"X-CSRF-Token":csrfToken}:{}), ...(fetchOptions.headers||{})}});
  const payload = await response.json();
  if (response.status === 401 && payload.login_required) {
    location.replace("/login");
    throw new Error("กรุณาเข้าสู่ระบบ");
  }
  if (!response.ok || (payload.ok === false && !allowErrorPayload)) throw new Error(payload.error || "เกิดข้อผิดพลาด");
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
    report: {
      server_name:$("serverName").value.trim(),
      alert_days:Number($("alertDays").value||7),
      report_hour:Number($("reportHour").value||9)
    }
  };
}

function setStatus(site, text, kind="idle") {
  const node = $(`${site}Status`); node.textContent=text; node.className=`status ${kind}`;
}

function result(message, ok=true) {
  const node=$("resultPanel"); node.textContent=message; node.className=`result-panel ${ok?"success":"error"}`;
}

function setCredentialPanel(site, passwordSaved, expanded=false) {
  const fields=$(`${site}Credentials`);
  const toggle=document.querySelector(`.credential-toggle[data-site="${site}"]`);
  fields.hidden=passwordSaved && !expanded;
  toggle.hidden=!passwordSaved;
  toggle.dataset.expanded=String(expanded);
  toggle.textContent=expanded?"ซ่อนบัญชี":"แสดง/แก้ไขบัญชี";
}

function toggleCredentialPanel(site) {
  const toggle=document.querySelector(`.credential-toggle[data-site="${site}"]`);
  setCredentialPanel(site,true,toggle.dataset.expanded!=="true");
}

async function loadSettings() {
  const {settings:s}=await api("/api/settings");
  $("version").textContent=`v${s.app.version}`;
  for (const site of ["primary","remote","sangfor"]) {
    $(`${site}Label`).value=s[site].label; $(`${site}Url`).value=s[site].url;
    $(`${site}Username`).value=s[site].username; $(`${site}Verify`).checked=s[site].verify_ssl;
    $(`${site}Saved`).textContent=s[site].password_saved?"บันทึกรหัสผ่านแล้ว":"ยังไม่ได้บันทึกรหัสผ่าน";
    setCredentialPanel(site,s[site].password_saved,false);
  }
  $("sangforEnabled").checked=s.sangfor.enabled;
  $("sangforBackupPath").value=s.sangfor.backup_path;
  $("serverName").value=s.report.server_name; $("alertDays").value=s.report.alert_days;
  $("reportHour").value=s.report.report_hour??9;
}

async function saveSettings() {
  const button=$("saveSettings"); button.disabled=true;
  try {
    const {settings}=await api("/api/settings",{method:"POST",body:JSON.stringify(allSettings())});
    for (const site of ["primary","remote","sangfor"]) {
      $(`${site}Password`).value="";
      $(`${site}Saved`).textContent=settings[site].password_saved?"บันทึกรหัสผ่านแล้ว":"ยังไม่ได้บันทึกรหัสผ่าน";
      setCredentialPanel(site,settings[site].password_saved,false);
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
    result(`ทดสอบ Sangfor สำเร็จ\nเรียง Latest Backup: ${response.sort_verified?"ล่าสุดไปเก่าสุด":"ยังไม่ยืนยัน"}\nผลล่าสุดแถวแรก: ${response.latest_backup_first||"-"}\nURL: ${response.url}\nภาพ: ${response.path}`);
  } catch(e) {
    setStatus("sangfor","Capture ไม่สำเร็จ","bad");
    result(e.message,false);
  } finally { button.disabled=false; }
}

async function testSites(sites) {
  return testWebCaptureSites(sites);
}

async function testWebCaptureSites(sites) {
  sites.forEach(s=>setStatus(s,"กำลัง Login และ Capture","busy"));
  try {
    const payload={sites}; sites.forEach(s=>payload[s]=sitePayload(s));
    const response=await api("/api/test",{method:"POST",body:JSON.stringify(payload),allowErrorPayload:true});
    const lines=[];
    for (const site of sites) {
      const item=response.results[site];
      if (!item.ok) {
        setStatus(site,"Web Capture ไม่สำเร็จ","bad");
        lines.push(`${site}: ${item.error}`);
      } else {
        setStatus(site,"Web Capture สำเร็จ","ok");
        lines.push(`${site}: Chromium Login และ Capture สำเร็จ\nภาพ: ${item.path}`);
      }
    }
    result(lines.join("\n\n"),response.ok);
  } catch(e) {
    sites.forEach(s=>setStatus(s,"Web Capture ไม่สำเร็จ","bad"));
    result(e.message,false);
  }
}

function downloadReport(url, filename) {
  const link=document.createElement("a");
  link.href=url;
  link.download=filename||"backup-report.pdf";
  link.hidden=true;
  document.body.append(link);
  link.click();
  link.remove();
}

function showDailySummary(response) {
  $("dailySummaryText").value=response.daily_summary||"";
  $("dailySummaryBox").hidden=false;
  const link=$("downloadDailySummary");
  link.href=`${response.summary_url}?token=${encodeURIComponent(token)}&download=1`;
  link.download=response.summary_name||"Backup_Daily_Summary.txt";
}

async function copyText(text, selectionField=null) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const field=selectionField||document.createElement("textarea");
    if (!selectionField) {
      field.value=text;
      field.style.position="fixed";
      field.style.opacity="0";
      document.body.append(field);
    }
    field.focus();
    field.select();
    document.execCommand("copy");
    if (selectionField) field.setSelectionRange(0,0);
    else field.remove();
  }
  toast("คัดลอกข้อความสรุปแล้ว");
}

async function copyDailySummary() {
  const field=$("dailySummaryText");
  await copyText(field.value,field);
}

async function generateReport() {
  return generateBrowserCaptureReport();
}

async function smokeCsv() {
  const button=$("smokeCsv"); button.disabled=true;
  setStatus("report","กำลัง Smoke Test CSV","busy");
  result("กำลัง Login File Station, ดาวน์โหลด และตรวจ CSV ของวันนี้...");
  try {
    const response=await api("/api/smoke-csv",{method:"POST",body:JSON.stringify({primary:sitePayload("primary")})});
    setStatus("report","Smoke Test CSV สำเร็จ","ok");
    result(`Smoke Test CSV ผ่าน\nชื่อไฟล์: ${response.name}\nขนาด: ${formatBytes(response.size)}\nSHA-256: ${response.sha256}\nรายการ: ${response.rows}\nCheck: ${response.check_count}\nแหล่ง: ${response.source_type}`);
  } catch(e) {
    setStatus("report","Smoke Test CSV ไม่สำเร็จ","bad");
    result(e.message,false);
  } finally { button.disabled=false; }
}

function fileToBase64(file) {
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(new Error("ไม่สามารถอ่านไฟล์ที่เลือกได้"));
    reader.onload=()=>resolve(String(reader.result).split(",",2)[1]||"");
    reader.readAsDataURL(file);
  });
}

function clearTaskListImage() {
  taskListClipboardFile=null;
  $("taskListImage").value="";
  if (taskListPreviewUrl) URL.revokeObjectURL(taskListPreviewUrl);
  taskListPreviewUrl="";
  $("taskListPreview").removeAttribute("src");
  $("taskListPreviewPanel").hidden=true;
  $("taskListPasteZone").classList.remove("has-image");
}

function setTaskListImage(file, source) {
  if (!file || !/^image\/(png|jpeg)$/i.test(file.type)) {
    result("ภาพ Task List ต้องเป็น PNG หรือ JPEG เท่านั้น",false);
    return false;
  }
  if (file.size > 12*1024*1024) {
    result("ภาพ Task List ต้องมีขนาดไม่เกิน 12 MB",false);
    return false;
  }
  taskListClipboardFile=file;
  if (taskListPreviewUrl) URL.revokeObjectURL(taskListPreviewUrl);
  taskListPreviewUrl=URL.createObjectURL(file);
  $("taskListPreview").src=taskListPreviewUrl;
  $("taskListImageStatus").textContent=`${source}: ${file.name} (${formatBytes(file.size)})`;
  $("taskListPreviewPanel").hidden=false;
  $("taskListPasteZone").classList.add("has-image");
  toast("รับภาพ Task List แล้ว");
  return true;
}

function pasteTaskListImage(event) {
  const item=Array.from(event.clipboardData?.items||[]).find(entry=>entry.kind==="file" && /^image\/(png|jpeg)$/i.test(entry.type));
  if (!item) return;
  const blob=item.getAsFile();
  if (!blob) return;
  event.preventDefault();
  const extension=blob.type.toLowerCase()==="image/jpeg"?"jpg":"png";
  setTaskListImage(new File([blob],`task-list-clipboard.${extension}`,{type:blob.type,lastModified:Date.now()}),"วางจาก Clipboard");
}

async function generateBrowserCaptureReport() {
  const button=$("generateReport");
  const file=$("activeBackupCsv").files[0];
  const taskListImage=taskListClipboardFile || $("taskListImage").files[0];
  if (file && !/^abb_daily_result_\d{4}-\d{2}-\d{2}\.csv$/i.test(file.name)) {
    result("ชื่อไฟล์ต้องเป็น abb_daily_result_YYYY-MM-DD.csv เท่านั้น",false);
    return;
  }
  button.disabled=true;
  setStatus("report","กำลังอ่าน CSV และ Capture หน้าเว็บ","busy");
  result("กำลังตรวจ CSV, Capture Active Backup Audit, Yard และ Sangfor ผ่าน Chromium...");
  try {
    const payload=allSettings();
    if (file) payload.active_backup_csv={name:file.name,content_base64:await fileToBase64(file)};
    if (taskListImage) payload.task_list_image={name:taskListImage.name,content_base64:await fileToBase64(taskListImage)};
    const response=await api("/api/generate",{method:"POST",body:JSON.stringify(payload)});
    setStatus("report","สร้างรายงานสำเร็จ","ok");
    result(`สร้างรายงานสำเร็จและเริ่มดาวน์โหลดแล้ว\nCSV: ${response.active_backup_source}\nแหล่ง CSV: ${response.active_backup_source_mode}\nภาพ Task List: ${response.task_list_image_attached?"แนบแล้ว":"ไม่ได้แนบ"}\nรายการ: ${response.rows}\nCheck: ${response.check_count}\nวิธีเก็บหลักฐาน: ${response.capture_method}\nไฟล์: ${response.path}`);
    showDailySummary(response);
    downloadReport(`${response.url}?token=${encodeURIComponent(token)}&download=1`,response.name);
    loadReportHistory();
  } catch(e) {
    setStatus("report","สร้างรายงานไม่สำเร็จ","bad");
    result(e.message,false);
  } finally {
    button.disabled=false;
  }
}

function formatBytes(bytes) {
  if (bytes >= 1024*1024) return `${(bytes/(1024*1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${bytes} Bytes`;
}

async function deleteReport(report) {
  if (!confirm(`ยืนยันลบรายงาน ${report.name}\n\nระบบจะลบเฉพาะ PDF และข้อความสรุปคู่กัน ไม่กระทบไฟล์ Backup บน NAS`)) return;
  const response=await api("/api/delete-report",{method:"POST",body:JSON.stringify({name:report.name})});
  toast(`ลบแล้ว ${response.removed.length} ไฟล์`);
  await loadReportHistory();
}

async function cleanupReports() {
  if (!confirm("ยืนยันลบรายงานที่เก่ากว่า 7 วันทั้งหมดหรือไม่?\n\nไฟล์ที่ลบแล้วจะกู้คืนผ่านหน้าเว็บไม่ได้ และไม่กระทบไฟล์ Backup บน NAS")) return;
  const button=$("cleanupReports"); button.disabled=true;
  try {
    const response=await api("/api/cleanup-reports",{method:"POST",body:"{}"});
    toast(response.file_count?`ลบรายงานเก่าแล้ว ${response.file_count} ไฟล์`:"ไม่พบรายงานที่เก่ากว่า 7 วัน");
    await loadReportHistory();
  } catch(e) {
    result(e.message,false);
  } finally { button.disabled=false; }
}

async function loadReportHistory() {
  const list=$("reportHistory");
  list.replaceChildren(Object.assign(document.createElement("div"),{className:"history-empty",textContent:"กำลังโหลดประวัติ..."}));
  try {
    const response=await api("/api/reports");
    const alerts=response.source_alerts||[];
    $("historySummary").textContent=`พบ ${response.reports.length} รายงาน และการแจ้งเตือนกติกาต้นทาง ${alerts.length} รายการ ภายใน ${response.days} วัน`;
    list.replaceChildren();
    for (const alert of alerts) {
      const item=document.createElement("div"); item.className="report-item source-contract-alert";
      const title=document.createElement("strong"); title.textContent="หยุดสร้างรายงาน: กติกาข้อมูลต้นทางเปลี่ยนหรือไฟล์ประจำวันไม่พร้อม";
      const time=document.createElement("small"); time.textContent=new Date(alert.observed_at).toLocaleString("th-TH");
      const message=document.createElement("pre"); message.textContent=alert.message;
      item.append(title,time,message); list.append(item);
    }
    if (!response.reports.length && !alerts.length) {
      list.append(Object.assign(document.createElement("div"),{className:"history-empty",textContent:"ยังไม่มีรายงานในช่วง 7 วันที่ผ่านมา"}));
      return;
    }
    for (const report of response.reports) {
      const item=document.createElement("div"); item.className="report-item";
      const itemHead=document.createElement("div"); itemHead.className="report-item-head";
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
      const remove=document.createElement("button"); remove.type="button"; remove.className="button danger"; remove.textContent="ลบรายงาน";
      remove.addEventListener("click",()=>deleteReport(report));
      actions.append(open,download,remove); itemHead.append(meta,actions);

      const summary=document.createElement("div"); summary.className="report-status-summary";
      const summaryHead=document.createElement("div"); summaryHead.className="report-status-head";
      const summaryTitle=document.createElement("strong"); summaryTitle.textContent="สรุปสถานะการออกรายงาน";
      summaryHead.append(summaryTitle);
      const summaryText=document.createElement("pre");
      if (report.summary_available) {
        summaryText.textContent=report.summary;
        const copy=document.createElement("button"); copy.type="button"; copy.className="button secondary compact-button";
        copy.textContent="คัดลอกข้อความ";
        copy.addEventListener("click",()=>copyText(report.summary));
        summaryHead.append(copy);
      } else {
        summary.classList.add("unavailable");
        summaryText.textContent="รายงานนี้ยังไม่มีข้อความสรุป เนื่องจากสร้างก่อนระบบสรุปรายวันรุ่น v0.8.6";
      }
      summary.append(summaryHead,summaryText);
      item.append(itemHead,summary); list.append(item);
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
document.querySelectorAll(".credential-toggle").forEach(b=>b.addEventListener("click",()=>toggleCredentialPanel(b.dataset.site)));
$("saveSettings").addEventListener("click",saveSettings);
$("testAll").addEventListener("click",()=>testSites(["primary","remote"]));
$("smokeCsv").addEventListener("click",smokeCsv);
$("generateReport").addEventListener("click",generateReport);
$("taskListImage").addEventListener("change",event=>{
  const file=event.target.files[0];
  if (file && !setTaskListImage(file,"เลือกไฟล์")) event.target.value="";
});
$("clearTaskListImage").addEventListener("click",clearTaskListImage);
document.addEventListener("paste",pasteTaskListImage);
$("copyDailySummary").addEventListener("click",copyDailySummary);
$("testSangfor").addEventListener("click",testSangfor);
document.querySelectorAll(".tab-button").forEach(button=>button.addEventListener("click",()=>selectTab(button.dataset.tab)));
$("refreshHistory").addEventListener("click",loadReportHistory);
$("cleanupReports").addEventListener("click",cleanupReports);
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
