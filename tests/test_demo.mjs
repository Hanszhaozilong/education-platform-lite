import test from 'node:test';
import assert from 'node:assert/strict';
import {createDemoData,monday,shiftDay,billableHours,conflict,recordAttendance} from '../docs/demo/assets/model.mjs';

test('demo dates follow the selected local calendar week across Sunday and month boundaries',()=>{
  assert.equal(monday('2026-10-20'),'2026-10-19');
  assert.equal(monday('2026-11-01'),'2026-10-26');
  assert.equal(shiftDay('2026-12-31',1),'2027-01-01');
});
test('fictional seed includes today and creates no teacher, student or room collisions',()=>{
  for(const day of ['2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23','2026-10-24','2026-10-25']){
    const data=createDemoData(day);
    assert.ok(data.lessons.some(item=>item.date===day));
    for(const item of data.lessons)assert.equal(conflict(data.lessons,item),'');
    assert.ok(data.people.every(item=>item.name.includes('演示')));
  }
});
test('lesson overlap checks each resource but permits adjacent lessons and different days',()=>{
  const first={id:1,date:'2026-10-20',start:'09:00',end:'11:00',teacherId:1,roomId:1,studentIds:[11]};
  const other={...first,id:2,start:'10:00',end:'12:00',teacherId:2,roomId:2,studentIds:[12]};
  assert.equal(conflict([first],other),'');
  assert.match(conflict([first],{...other,teacherId:1}),/教师/);
  assert.match(conflict([first],{...other,roomId:1}),/教室/);
  assert.match(conflict([first],{...other,studentIds:[11]}),/学生/);
  assert.equal(conflict([first],{...first,id:2,start:'11:00',end:'13:00'}),'');
  assert.equal(conflict([first],{...first,id:2,date:'2026-10-21'}),'');
  assert.match(conflict([],{...first,start:'12:00',end:'11:00'}),/结束/);
});
test('attendance rounds upward by half an hour and updates without creating duplicates',()=>{
  assert.deepEqual([0,1,30,31,60,61,120].map(billableHours),[0,.5,.5,1,1,1.5,2]);
  const data=createDemoData('2026-10-20');
  recordAttendance(data,1,[{studentId:11,status:'present',minutes:31}]);
  recordAttendance(data,1,[{studentId:11,status:'present',minutes:61}]);
  assert.equal(data.attendances.length,1);
  assert.equal(data.attendances[0].hours,1.5);
});
