// Education Platform Lite demo · 泪见雪. · Fictional browser-local data only.
export const SUBJECTS = ['语文', '数学', '英语', '物理', '化学', '生物', '历史', '地理', '政治'];
export const ROLES = {admin: '超级管理员', principal: '校长', teacher: '教师', student: '学生'};
export const GRADES = ['小学一年级','小学二年级','小学三年级','小学四年级','小学五年级','小学六年级','初一','初二','初三','高一','高二','高三'];
export function isoDay(value = new Date()) {
  const d = new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
export function shiftDay(day, offset) { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate()+offset); return isoDay(d); }
export function monday(day) { return shiftDay(day, -(new Date(`${day}T12:00:00`).getDay()+6)%7); }
export function billableHours(minutes) { return minutes > 0 ? Math.ceil(minutes/30)/2 : 0; }
export function conflict(lessons, candidate) {
  if (!candidate.studentIds.length) return '请至少选择一名学生。';
  if (!candidate.start || !candidate.end || candidate.start >= candidate.end) return '结束时间需要晚于开始时间。';
  for (const item of lessons) {
    if (item.id === candidate.id || item.date !== candidate.date || item.start >= candidate.end || candidate.start >= item.end) continue;
    if (item.teacherId === candidate.teacherId) return '该教师在此时段已有课程，请调整时间。';
    if (candidate.roomId && item.roomId === candidate.roomId) return '该教室在此时段已有课程，请选择其他教室。';
    if (item.studentIds.some(id => candidate.studentIds.includes(id))) return '所选学生在此时段已有课程，请调整时间。';
  }
  return '';
}
export function recordAttendance(data, lessonId, rows) {
  data.attendances = data.attendances.filter(item => item.lessonId !== lessonId);
  data.attendances.push(...rows.map(row => ({...row, lessonId, hours: billableHours(row.minutes)})));
}
export function createDemoData(today = isoDay()) {
  const week = monday(today);
  const data = {
    version: 1,
    people: [
      {id:1,role:'teacher',name:'林知远（演示）',subjects:['数学','物理'],phone:'138****1001',note:'虚构示例：5 年教学经验；示例师范大学；全职任教。'},
      {id:2,role:'teacher',name:'许清和（演示）',subjects:['英语'],phone:'138****1002',note:'虚构示例：3 年教学经验；示例外国语大学。'},
      {id:3,role:'teacher',name:'周予安（演示）',subjects:['语文'],phone:'138****1003',note:'虚构示例：6 年教学经验。'},
      ...['陈星禾','苏沐阳','江小满','温以宁','宋予川','陆明朗'].map((name,i)=>({id:11+i,role:'student',name:`${name}（演示）`,grade:7+i%3,phone:`139****200${i+1}`,owner:i%2?'父亲':'母亲',note:'虚构示例：周末到校，关注学习习惯。'})),
      {id:21,role:'principal',name:'沈校长（演示）',phone:'138****3001',note:'虚构示例：负责日常教务与招生。'}
    ],
    rooms:[{id:1,name:'1号教室',status:'free',note:''},{id:2,name:'2号教室',status:'occupied',note:'演示：临时自习中'},{id:3,name:'3号教室',status:'free',note:''},{id:4,name:'4号教室',status:'maintenance',note:'演示：投影设备检修'}],
    lessons:[], attendances:[],
    leads:[
      {id:1,name:'顾同学（演示）',phone:'139****4001',grade:8,status:'trial',note:'已沟通，预约两门科目试听。',trials:[{subject:'数学',teacherId:1,date:shiftDay(week,5),time:'11:00'},{subject:'英语',teacherId:2,date:shiftDay(week,5),time:'15:00'}]},
      {id:2,name:'夏同学（演示）',phone:'139****4002',grade:7,status:'new',note:'等待家长确认到校时间。',trials:[]},
      {id:3,name:'叶同学（演示）',phone:'139****4003',grade:9,status:'lost',note:'目前时间不合适，后续可恢复跟进。',trials:[]}
    ],
    notices:[{id:1,title:'欢迎体验教培教务平台精简版',body:'本演示站展示排课、人员管理、手动考勤、教室状态和试听 CRM。所有人员、联系方式和课程均为虚构数据。',date:today},{id:2,title:'周末教学安排提醒',body:'请提前核对课程与教室安排。授课结束后，可进入课程详情登记考勤和实际分钟数。',date:shiftDay(today,-1)}]
  };
  const slots=[[0,'16:00','18:00',1,'数学',[11],1],[2,'17:00','19:00',2,'英语',[12],2],[4,'19:00','21:00',3,'语文',[13],3],[5,'09:00','11:00',1,'数学',[11,12],1],[5,'13:00','15:00',2,'英语',[13,14],2],[5,'17:00','19:00',3,'语文',[15],3],[6,'10:00','12:00',1,'物理',[12],1],[6,'15:00','17:00',2,'英语',[11,16],2]];
  slots.push([(new Date(`${today}T12:00:00`).getDay()+6)%7,'09:00','11:00',3,'语文',[14,16],3]);
  data.lessons=slots.map(([day,start,end,teacherId,subject,studentIds,roomId],i)=>({id:i+1,date:shiftDay(week,day),start,end,teacherId,subject,studentIds,roomId,note:'虚构演示课程'}));
  return data;
}
