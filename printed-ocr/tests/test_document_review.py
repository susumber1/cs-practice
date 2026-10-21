import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from document_batch import Задание, РезультатФайла, СеансРаспознавания
from document_review import исправить_по_словарю, сверить_комплект, поля


def result(category, text, filename=None, raw=''):
    return РезультатФайла(Задание(category, Path('/tmp')/(filename or category+'.jpg')),
                          текст=text, исходный_текст=raw)


class ReviewTests(unittest.TestCase):
    def test_scoped_dictionaries_and_passthrough(self):
        for category, text, expected in (
            ('diploma','АИПАОМ БАКАААВРА С ОТАИЧИЕМ','ДИПЛОМ БАКАЛАВРА С ОТЛИЧИЕМ'),
            ('diploma_supplement','Дисциплнны: Математнка 108; отлнчно','Дисциплины: Математика 108; отлично'),
            ('curriculum','Лекцни 36; самостоятехьная работа 72','Лекции 36; самостоятельная работа 72'),
        ):
            corrected, log=исправить_по_словарю(text,category)
            self.assertEqual(corrected,expected)
            self.assertTrue(log)
            self.assertEqual(исправить_по_словарю(corrected,category),(corrected,()))
        s='Математнка 108\nФамилия: Дисциплнна'
        self.assertEqual(исправить_по_словарю(s,'foreign_passport'),(s,()))
        self.assertEqual(исправить_по_словарю('Фамилия: Дисциплнна','curriculum')[0],'Фамилия: Дисциплнна')

    def test_docx_confirms_one_ocr_letter_and_audits(self):
        records=[result('curriculum','Программирование 108','plan.docx'),
                 result('diploma_supplement','Программированне 108')]
        checked,report=сверить_комплект(records)
        self.assertEqual(checked[1].текст,'Программирование 108')
        self.assertIn('plan.docx',report)
        self.assertIn('«Программированне» → «Программирование»',report)
        self.assertEqual(records[1].текст,'Программированне 108')
        self.assertEqual(checked[0],records[0])

    def test_lone_photo_cannot_override_other_photo(self):
        records=[result('curriculum','Программирование'),
                 result('diploma_supplement','Программированне')]
        checked,_=сверить_комплект(records)
        self.assertEqual(checked,records)

    def test_two_files_two_sections_can_confirm(self):
        records=[result('curriculum','Программирование'),
                 result('diploma_supplement','Программирование','supp1.jpg'),
                 result('diploma_supplement','Программированне','supp2.jpg')]
        checked,_=сверить_комплект(records)
        self.assertEqual(checked[2].текст,'Программирование')

    def test_duplicate_file_is_not_independent_evidence(self):
        records=[result('curriculum','Программирование','same.jpg'),
                 result('diploma_supplement','Программирование','same.jpg'),
                 result('diploma_supplement','Программированне','other.jpg')]
        self.assertEqual(сверить_комплект(records)[0],records)

    def test_generated_correction_is_not_evidence(self):
        records=[result('curriculum','Программирование',raw='Другой текст'),
                 result('diploma_supplement','Программирование','one.jpg',raw='Другой текст'),
                 result('diploma_supplement','Программированне','two.jpg')]
        self.assertEqual(сверить_комплект(records)[0],records)

    def test_passport_identity_conflict_stops_rewrites(self):
        records=[result('foreign_passport','ФИО: Иванов Иван Иванович'),
                 result('diploma','ФИО: Петров Иван Иванович'),
                 result('curriculum','Программирование','plan.docx'),
                 result('diploma_supplement','Программированне')]
        checked,report=сверить_комплект(records)
        self.assertEqual(checked,records)
        self.assertIn('[ПРОВЕРЬТЕ] ФИО',report)
        self.assertIn('отключены',report)

    def test_numeric_conflicts_never_rewritten(self):
        records=[result('diploma','Серия и номер: 106104 0070776'),
                 result('diploma_supplement','Серия и номер диплома: 106104 0070778'),
                 result('foreign_passport','Номер паспорта: 123456789')]
        checked,report=сверить_комплект(records)
        self.assertEqual(checked,records)
        self.assertIn('[ПРОВЕРЬТЕ] Серия и номер диплома',report)
        self.assertNotIn('Номер паспорта',report)

    def test_template_identity_matches_separate_passport_fields(self):
        records=[result('diploma','Настоящий диплом свидетельствует о том, что\nТкачев\nРадомир Святославович\nосвоил(а) программу\n09.03.04 Программная инженерия\nприсвоена(ы) квалификация(и)\nБакалавр'),
                 result('foreign_passport','Фамилия: Ткачев\nИмя: Радомир\nОтчество: Святославович')]
        _,report=сверить_комплект(records)
        self.assertIn('Совпадает: ФИО',report)
        self.assertNotIn('[ПРОВЕРЬТЕ]',report)
        self.assertIn('Квалификация',{p.вид for p in поля(records[0].текст,'diploma')})

    def test_partial_and_empty_review_is_honest(self):
        bad=РезультатФайла(Задание('diploma',Path('/tmp/bad.jpg')),ошибка='broken')
        checked,report=сверить_комплект([bad],неполный=True)
        self.assertEqual(checked,[bad])
        self.assertIn('неполная',report)
        self.assertIn('не подтверждает',report)

    def test_docx_not_rewritten_and_names_protected(self):
        records=[result('curriculum','Программирование','reference.docx'),
                 result('curriculum','Программированне','source.docx'),
                 result('foreign_passport','Программированне'),
                 result('diploma_supplement','Фамилия: Программированне')]
        self.assertEqual(сверить_комплект(records)[0],records)

    def test_real_ocr_pipeline_dictionary_callback_before_language_model(self):
        from PIL import Image
        import raspoznat_pechat as engine
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.jpg'
            Image.new('RGB',(100,50),'white').save(path)
            session=СеансРаспознавания()
            session._ocr=engine
            session._распознаватель=object()
            model=Mock()
            model.исправить.side_effect=lambda text,**kw:text
            session._корректор=model
            with patch.object(engine,'распознать_страницу',return_value='Лекцни 36'):
                text=session.обработать(Задание('curriculum',path))
            self.assertEqual(text,'Лекции 36')
            self.assertEqual(session.исходный_текст,'Лекцни 36')
            self.assertTrue(session.последние_правки)
            model.исправить.assert_called_once_with('Лекции',разрешить_имена=True)

    def test_hours_require_named_columns_and_do_not_mix_with_credits(self):
        records=[result('curriculum','Дисциплина | Часы\nМатематика | 108','plan.docx'),
                 result('diploma_supplement','Дисциплина | Часы\nМатематика | 180')]
        checked,report=сверить_комплект(records)
        self.assertEqual(checked,records)
        self.assertIn('[ПРОВЕРЬТЕ] Часы: математика',report)
        credits=records[:1]+[result('diploma_supplement','Дисциплина | Зачетные единицы\nМатематика | 3')]
        self.assertNotIn('[ПРОВЕРЬТЕ] Часы',сверить_комплект(credits)[1])

    def test_review_replaces_visible_text_and_is_exported(self):
        from interface import ПриложениеOCR
        from document_batch import собрать_результаты
        ui=ПриложениеOCR.__new__(ПриложениеOCR)
        ui.очередь=queue.Queue(); ui.остановка=threading.Event(); ui.занято=True
        ui.результат=Mock(); ui.кнопка_стоп=Mock(); ui.статус=Mock()
        ui._обновить_кнопки=Mock(); ui._обновить_экспорт=Mock()
        records=[result('curriculum','Программирование')]
        report='СВЕРКА КОМПЛЕКТА\nСовпадает'
        ui.очередь.put(('сверка',(records,report)))
        ui.очередь.put(('завершено',(False,1)))
        ui._проверить_очередь()
        expected=собрать_результаты(records)+'\n\n'+report
        ui.результат.insert.assert_called_once_with('1.0',expected)
        self.assertEqual(ui._число_символов,len(expected))
        self.assertFalse(ui.занято)
        self.assertEqual(ui.результаты,records)
        ui.результат.get.return_value=expected
        self.assertEqual(ui._получить_текст(),expected)

    def test_worker_review_order_disable_and_stop(self):
        from interface import ПриложениеOCR
        for enabled in (True,False):
            ui=ПриложениеOCR.__new__(ПриложениеOCR)
            ui.очередь=queue.Queue(); ui.остановка=threading.Event()
            ui.сеанс=Mock(последние_правки=(),исходный_текст='text')
            ui.сеанс.обработать.return_value='text'
            jobs=(Задание('curriculum',Path('/tmp/test.jpg')),)
            ui._распознать_в_фоне(jobs,True,False,enabled)
            events=[]
            while not ui.очередь.empty(): events.append(ui.очередь.get()[0])
            self.assertEqual(events[-1],'завершено')
            self.assertEqual('сверка' in events,enabled)
            self.assertEqual(events[0],'результат')
        ui.остановка.clear()
        def stop(*args,**kwargs):
            ui.остановка.set()
            return 'text'
        ui.сеанс.обработать.side_effect=stop
        ui._распознать_в_фоне(jobs*2,True,False,True)
        events=[]
        while not ui.очередь.empty(): events.append(ui.очередь.get())
        self.assertEqual(sum(t=='результат' for t,_ in events),1)
        self.assertIn('неполная',next(d[1] for t,d in events if t=='сверка'))


if __name__=='__main__': unittest.main()
