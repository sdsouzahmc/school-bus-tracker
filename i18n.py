"""English / Arabic interface text. Keys are the English strings; missing Arabic falls back to English."""
import streamlit as st

AR = {
    # login & shell
    "School Bus Tracker": "متتبع الحافلات المدرسية",
    "Sign in": "تسجيل الدخول",
    "Username": "اسم المستخدم",
    "PIN / password": "الرمز / كلمة المرور",
    "Sign out": "تسجيل الخروج",
    "Language": "اللغة",
    "Verification code": "رمز التحقق",
    "Verify": "تحقق",
    "Wrong username or PIN.": "اسم المستخدم أو الرمز غير صحيح.",
    "Wrong code.": "رمز غير صحيح.",
    # crew
    "Crew app": "تطبيق الطاقم",
    "Start trip": "بدء الرحلة",
    "Trip": "الرحلة",
    "Bus": "الحافلة",
    "Driver": "السائق",
    "Supervisor": "المشرف",
    "Care-taker": "المرافِقة",
    "Confirm crew on board": "تأكيد الطاقم في الحافلة",
    "Current stop": "الموقف الحالي",
    "School": "المدرسة",
    "Check In": "تسجيل صعود",
    "Check Out": "تسجيل نزول",
    "Scan badge with camera": "مسح البطاقة بالكاميرا",
    "Badge reader / type code": "قارئ البطاقة / إدخال الرمز",
    "Manual entry": "إدخال يدوي",
    "Badge code": "رمز البطاقة",
    "Submit": "إرسال",
    "Reason": "السبب",
    "Verified by": "تم التحقق بواسطة",
    "Student": "الطالب",
    "Received by (school staff)": "استلمه (موظف المدرسة)",
    "Handed to (authorized recipient)": "سُلّم إلى (مستلم معتمد)",
    "No approved recipient present": "لا يوجد مستلم معتمد",
    "Confirm handover": "تأكيد التسليم",
    "Mark no-show": "تسجيل عدم حضور",
    "On board": "في الحافلة",
    "Expected": "متوقع",
    "Completed": "مكتمل",
    "Close trip": "إغلاق الرحلة",
    "Physical sweep done by": "تم تفتيش الحافلة بواسطة",
    "I walked the full bus and checked every seat": "تجولت في الحافلة كاملة وفحصت كل مقعد",
    "Offline mode": "وضع عدم الاتصال",
    "get off at this stop": "ينزلون في هذه المحطة",
    "Refresh": "تحديث",
    "Absent": "غائب",
    "Which trip are you starting?": "أي رحلة تبدأ؟",
    "Crew": "الطاقم",
    "tap to change": "اضغط للتغيير",
    "All stops done": "انتهت كل المحطات",
    "sweep the bus and close the trip below.": "افحص الحافلة وأغلق الرحلة بالأسفل.",
    "Next stop": "المحطة التالية",
    "Go to": "اذهب إلى",
    "You are at": "أنت في",
    "nothing to do here": "لا شيء هنا",
    "to get off": "للنزول",
    "to board": "للصعود",
    "children expected at this stop": "الأطفال المتوقعون في هذه المحطة",
    "GPS unavailable": "تحديد الموقع غير متاح",
    "Sync now": "مزامنة الآن",
    "Pending sync": "بانتظار المزامنة",
    "Drivers do not scan. This screen is read-only for the driver.": "السائق لا يقوم بالمسح. هذه الشاشة للعرض فقط للسائق.",
    "Download encrypted roster": "تنزيل القائمة المشفرة",
    "Printable contingency roster": "قائمة احتياطية للطباعة",
    "Still to be accounted for": "لم يتم حصرهم بعد",
    "Cannot close: every child must be accounted for.": "لا يمكن الإغلاق: يجب حصر جميع الأطفال.",
    # parent
    "My children": "أطفالي",
    "Status": "الحالة",
    "Last update": "آخر تحديث",
    "Last bus location": "آخر موقع للحافلة",
    "Declare absence": "الإبلاغ عن غياب",
    "Request a change": "طلب تغيير",
    "Messages": "الرسائل",
    "Date": "التاريخ",
    "All trips": "جميع الرحلات",
    "Send": "إرسال",
    "Change type": "نوع التغيير",
    "Different stop": "موقف مختلف",
    "Different bus": "حافلة مختلفة",
    "One-day recipient": "مستلم ليوم واحد",
    "Recipient name": "اسم المستلم",
    "Recipient phone": "هاتف المستلم",
    "Note": "ملاحظة",
    "Request sent to the transport office.": "تم إرسال الطلب إلى مكتب النقل.",
    "Absence recorded. The crew will not wait for your child.": "تم تسجيل الغياب. لن ينتظر الطاقم طفلك.",
    "Delayed update — the bus device was offline; this was received later.": "تحديث متأخر — كان جهاز الحافلة غير متصل وتم الاستلام لاحقًا.",
    "Urgent? Do not rely on the app — call the transport office:": "أمر عاجل؟ لا تعتمد على التطبيق — اتصل بمكتب النقل:",
    "Today's journey": "رحلة اليوم",
    "No trips yet today.": "لا توجد رحلات اليوم بعد.",
    "Boarded": "صعد",
    "Got off": "نزل",
    "Handover": "التسليم",
    # statuses
    "Declared absent": "غياب مُبلغ عنه",
    "No show": "لم يحضر",
    "Returned to school": "أُعيد إلى المدرسة",
    "Awaiting transfer approval": "بانتظار الموافقة على النقل",
    "Transferred to other bus": "نُقل إلى حافلة أخرى",
    "Not travelling today": "لا يوجد تنقل اليوم",
    "Action": "الإجراء",
    "Class": "الصف",
    "Purpose": "الغرض",
    "Stop": "الموقف",
    "Batch": "الدفعة",
    "Group": "المجموعة",
    "Pickup": "صعود من المنزل",
    "Dropoff": "توصيل إلى المنزل",
    "Handed to": "سُلّم إلى",
    "Received by": "استلمه",
    "expected at this stop": "متوقع في هذا الموقف",
    "All children on this trip": "جميع الأطفال في هذه الرحلة",
    "Scan log": "سجل المسح",
    # receipt
    "School receipt": "الاستلام في المدرسة",
    "Arriving buses": "الحافلات القادمة",
}


def lang():
    return st.session_state.get("lang", "en")


def t(text):
    return AR.get(text, text) if lang() == "ar" else text


def rtl_css():
    if lang() != "ar":
        return ""
    return """<style>
      .stMainBlockContainer, [data-testid="stSidebarContent"] { direction: rtl; text-align: right; }
      [data-testid="stDataFrame"], .stDataFrame, pre, code { direction: ltr; text-align: left; }
    </style>"""
