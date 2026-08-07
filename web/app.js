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
  sites.forEach(s=>setStatus(s,"กำลังเชื่อมต่อ","busy"));
  try {
    const payload={sites}; sites.forEach(s=>payload[s]=sitePayload(s));
    const response=await api("/api/test",{method:"POST",body:JSON.stringify(payload)});
    for (const site of sites) {
      const item=response.results[site];
      if (!item.ok) {
        setStatus(site,"เชื่อมต่อไม่สำเร็จ","bad");
      } else if (site === "remote" && item.data_ready === false) {
        const warningText=item.readiness === "no_connections"
          ? "ShareSync - พบ 0 โฟลเดอร์"
          : item.readiness === "paused"
            ? "ShareSync - งานถูกพัก"
            : "ShareSync - ต้องตรวจสอบ";
        setStatus(site,warningText,"warn");
      } else if (site === "primary" && item.active_backup_cross_check && !item.active_backup_cross_check.consistent) {
        setStatus(site,`CSV พร้อมใช้ / API ต่าง ${item.active_backup_cross_check.warning_count} รายการ`,"warn");
      } else {
        setStatus(site,site === "remote"?`ShareSync ${item.up_to_date_count}/${item.connection_count} Up to date`:`NAS CSV ${item.row_count} rows / API ตรงกัน`,"ok");
      }
    }
    const lines=Object.entries(response.results).map(([site,item])=>item.ok
      ? `${item.label}: OK\nAPI: ${item.available_apis.join(", ")}${site === "remote"?`\nDrive ShareSync folders: ${item.connection_count}\nUp to date: ${item.up_to_date_count}\nOverall status: ${item.tray_status}${item.data_ready?"":"\nคำเตือน: มีรายการ Drive ShareSync ที่ต้องตรวจสอบ"}`:`\nNAS CSV rows: ${item.row_count}\nCheck from CSV: ${item.check_count}\nAPI cross-check: ${item.active_backup_cross_check.consistent?"MATCHED":`WARNING ${item.active_backup_cross_check.warning_count}`}\n${(item.active_backup_cross_check.warnings||[]).join("\n")}`}${item.security_warning?"\nคำเตือน: URL ยังเป็น HTTP":""}`
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
  const button=$("generateReport"); button.disabled=true;
  setStatus("report","กำลังดึงข้อมูลจาก NAS","busy");
  result("กำลังอ่าน Active Backup และ Drive ShareSync ผ่าน Web API แล้วสร้าง PDF...");
  try {
    const response=await api("/api/generate",{method:"POST",body:JSON.stringify(allSettings())});
    setStatus("report","สร้างรายงานสำเร็จ","ok");
    result(`สร้างรายงานสำเร็จและเริ่มดาวน์โหลดไฟล์แล้ว\nรอบข้อมูลถึง: ${response.data_cutoff}\nผล Active Backup ล่าสุดจาก NAS: ${response.latest_result_time||"ไม่พบในรอบ"}\nสถานะรายงาน: ${response.is_final_window?"รอบ 09:00 สมบูรณ์":"ฉบับก่อน 09:00"}\nรายการ Active Backup: ${response.rows}\nงานไม่มีผลในรอบ: ${response.missing_task_count}\nสถานะ Check จาก NAS: ${response.check_count}\nYard Drive ShareSync: ${response.cloud_sync.up_to_date_count}/${response.cloud_sync.connection_count} Up to date\nYard logs: ${(response.cloud_sync.logs||[]).length}\nSangfor capture: ${response.sangfor.enabled?("แนบแล้ว; Latest Backup "+(response.sangfor.sort_verified?"เรียงล่าสุดไปเก่าสุด":"ยังไม่ยืนยัน")):"ไม่ได้เปิดใช้"}\nไฟล์: ${response.path}`);
    const abbCheck=response.active_backup_cross_check;
    if (abbCheck && !abbCheck.consistent) {
      result(`สร้าง PDF จาก CSV สำเร็จ แต่ Active Backup API พบความแตกต่าง ${abbCheck.warning_count} รายการ\nCSV ยังคงเป็นข้อมูลหลักและไม่ได้ถูกแก้ทับ\n${(abbCheck.warnings||[]).join("\n")}`,false);
    }
    showDailySummary(response);
    downloadReport(`${response.url}?token=${encodeURIComponent(token)}&download=1`,response.name);
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
    $("historySummary").textContent=`พบ ${response.reports.length} รายงานภายใน ${response.days} วัน`;
    list.replaceChildren();
    if (!response.reports.length) {
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
document.querySelectorAll(".probe-button").forEach(b=>b.addEventListener("click",()=>probe(b.dataset.site)));
document.querySelectorAll(".credential-toggle").forEach(b=>b.addEventListener("click",()=>toggleCredentialPanel(b.dataset.site)));
$("saveSettings").addEventListener("click",saveSettings);
$("testAll").addEventListener("click",()=>testSites(["primary","remote"]));
$("generateReport").addEventListener("click",generateReport);
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
