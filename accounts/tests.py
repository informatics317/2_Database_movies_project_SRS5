from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Genre, Mark, Movie, Rating, Review


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FilmsTests(TestCase):
    def setUp(self):
        self.drama = Genre.objects.create(name='Драма')
        self.comedy = Genre.objects.create(name='Комедия')
        self.crime = Genre.objects.create(name='Криминал')

        self.m1 = Movie.objects.create(
            title='Побег из Шоушенка', year=1994, director='Фрэнк Дарабонт',
            duration=142, rating=Decimal('9.3'))
        self.m1.genres.add(self.drama)

        self.m2 = Movie.objects.create(
            title='Форрест Гамп', year=1994, director='Роберт Земекис',
            duration=142, rating=Decimal('8.8'))
        self.m2.genres.add(self.drama, self.comedy)

        self.m3 = Movie.objects.create(
            title='Леон', year=1994, director='Люк Бессон',
            duration=110, rating=Decimal('8.5'))
        self.m3.genres.add(self.crime, self.drama)

        self.user = User.objects.create_user('anna', password='User12345!')
        self.admin = User.objects.create_superuser('admin', password='Admin12345!')
        self.client.login(username='anna', password='User12345!')


    def test_pages_require_login(self):
        self.client.logout()
        for name in ('catalog', 'search', 'stats', 'my_all', 'my_watch', 'movie_partial'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse('login'), response['Location'], name)

    def test_register_and_login(self):
        self.client.logout()
        response = self.client.post(reverse('register'), {
            'username': 'newbie', 'password1': 'Strong-pass-77', 'password2': 'Strong-pass-77'})
        self.assertRedirects(response, reverse('catalog'))
        self.assertTrue(User.objects.filter(username='newbie').exists())
        self.assertEqual(self.client.get(reverse('catalog')).status_code, 200)

    def test_logout_is_post_and_works(self):
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        self.assertEqual(self.client.get(reverse('catalog')).status_code, 302)


    def test_pages_open(self):
        for name in ('catalog', 'search', 'stats', 'my_all', 'my_watch', 'my_favorite', 'my_watched'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        url = reverse('movie_detail', args=[self.m1.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_no_template_leftovers_on_pages(self):
        urls = [reverse(n) for n in ('catalog', 'search', 'stats', 'my_all', 'my_watch')]
        urls.append(reverse('movie_detail', args=[self.m1.pk]))
        for url in urls:
            html = self.client.get(url).content.decode()
            self.assertNotIn('{#', html, url)
            self.assertNotIn('{%', html, url)

    def test_footer_text_removed(self):
        html = self.client.get(reverse('catalog')).content.decode()
        self.assertNotIn('учебный проект на Django', html)
        self.assertNotIn('Режим экрана', html)


    def test_search_is_case_insensitive_for_cyrillic(self):
        url = reverse('movie_partial')
        for query in ('побег', 'ПОБЕГ', 'дарабонт'):
            data = self.client.get(url, {'q': query}).json()
            self.assertEqual(data['count'], 1, query)

    def test_several_genres_any_and_all(self):
        url = reverse('movie_partial')
        both = f'{self.comedy.pk},{self.crime.pk}'
        self.assertEqual(self.client.get(url, {'genres': both, 'mode': 'any'}).json()['count'], 2)
        self.assertEqual(self.client.get(url, {'genres': both, 'mode': 'all'}).json()['count'], 0)
        drama_crime = f'{self.drama.pk},{self.crime.pk}'
        self.assertEqual(self.client.get(url, {'genres': drama_crime, 'mode': 'all'}).json()['count'], 1)
        self.assertEqual(self.client.get(url, {'genres': str(self.drama.pk)}).json()['count'], 3)

    def test_bad_sort_and_genres_do_not_break(self):
        url = reverse('movie_partial')
        data = self.client.get(url, {'sort': 'bad; DROP', 'genres': 'x,,1a', 'mode': 'zzz'}).json()
        self.assertEqual(data['count'], 3)


    def test_toggle_mark_and_my_pages(self):
        url = reverse('toggle_mark', args=[self.m1.pk, 'favorite'])
        self.assertEqual(self.client.get(url).status_code, 405)  # только POST

        data = self.client.post(url).json()
        self.assertTrue(data['active'])
        self.assertEqual(data['counts']['favorite'], 1)
        self.assertEqual(data['counts']['all'], 1)

        self.client.post(reverse('toggle_mark', args=[self.m1.pk, 'watch']))
        data = self.client.post(reverse('toggle_mark', args=[self.m2.pk, 'watch'])).json()
        self.assertEqual(data['counts']['watch'], 2)
        self.assertEqual(data['counts']['all'], 2)   # m1 отмечен дважды, но это один фильм

        partial = reverse('movie_partial')
        self.assertEqual(self.client.get(partial, {'kind': 'favorite'}).json()['count'], 1)
        self.assertEqual(self.client.get(partial, {'kind': 'watch'}).json()['count'], 2)
        self.assertEqual(self.client.get(partial, {'kind': 'all'}).json()['count'], 2)
        self.assertEqual(self.client.get(partial, {'kind': 'watched'}).json()['count'], 0)

        data = self.client.post(url).json()
        self.assertFalse(data['active'])
        self.assertEqual(self.client.get(partial, {'kind': 'favorite'}).json()['count'], 0)

    def test_unknown_mark_kind_rejected(self):
        url = reverse('toggle_mark', args=[self.m1.pk, 'bad'])
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_marks_are_private_for_each_user(self):
        self.client.post(reverse('toggle_mark', args=[self.m1.pk, 'favorite']))
        self.client.logout()
        self.client.login(username='admin', password='Admin12345!')
        data = self.client.get(reverse('movie_partial'), {'kind': 'favorite'}).json()
        self.assertEqual(data['count'], 0)


    def test_rating_is_independent_of_review(self):
        url = reverse('rate_movie', args=[self.m1.pk])
        data = self.client.post(url, {'score': 9}).json()
        self.assertEqual(data['my_score'], 9)
        self.assertEqual(data['ratings_count'], 1)
        self.assertEqual(data['avg_score'], 9.0)
        self.assertEqual(Review.objects.count(), 0)    # отзыва нет, а оценка есть

        data = self.client.post(url, {'score': 7}).json()
        self.assertEqual(data['my_score'], 7)
        self.assertEqual(Rating.objects.count(), 1)

        data = self.client.post(url, {'score': 7}).json()
        self.assertIsNone(data['my_score'])
        self.assertEqual(data['ratings_count'], 0)
        self.assertIsNone(data['avg_score'])

    def test_invalid_rating_rejected(self):
        url = reverse('rate_movie', args=[self.m1.pk])
        for bad in ('0', '11', 'abc', ''):
            self.assertEqual(self.client.post(url, {'score': bad}).status_code, 400, bad)
        self.assertEqual(Rating.objects.count(), 0)

    def test_stats_chart_numbers(self):
        Rating.objects.create(user=self.user, movie=self.m1, score=9)
        Rating.objects.create(user=self.user, movie=self.m2, score=9)
        Rating.objects.create(user=self.admin, movie=self.m1, score=3)
        response = self.client.get(reverse('stats'))
        self.assertEqual(response.context['score_numbers'], [0, 0, 1, 0, 0, 0, 0, 0, 2, 0])
        self.assertEqual(response.context['ratings_total'], 3)


    def test_add_and_delete_review(self):
        url = reverse('add_review', args=[self.m1.pk])
        response = self.client.post(url, {'text': 'Отличный фильм'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['reviews_count'], 1)

        review = Review.objects.get()
        self.assertEqual(review.user, self.user)
        self.assertEqual(Rating.objects.count(), 0)

        data = self.client.post(reverse('delete_review', args=[review.pk])).json()
        self.assertEqual(data['reviews_count'], 0)

    def test_empty_review_rejected(self):
        url = reverse('add_review', args=[self.m1.pk])
        response = self.client.post(url, {'text': ''})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertEqual(Review.objects.count(), 0)

    def test_only_author_or_admin_deletes_review(self):
        review = Review.objects.create(movie=self.m1, user=self.admin, text='Текст админа')
        url = reverse('delete_review', args=[review.pk])
        self.assertEqual(self.client.post(url).status_code, 403)    # чужой отзыв
        self.assertEqual(Review.objects.count(), 1)

        mine = Review.objects.create(movie=self.m1, user=self.user, text='Мой отзыв')
        self.assertEqual(self.client.post(reverse('delete_review', args=[mine.pk])).status_code, 200)

        self.client.logout()
        self.client.login(username='admin', password='Admin12345!')
        self.assertEqual(self.client.post(url).status_code, 200)


    def test_regular_user_cannot_add_or_delete_movies(self):
        response = self.client.get(reverse('movie_add'))
        self.assertRedirects(response, reverse('catalog'))

        count = Movie.objects.count()
        self.client.post(reverse('movie_add'), {'title': 'Взлом', 'year': 2000})
        self.assertEqual(Movie.objects.count(), count)

        response = self.client.post(reverse('delete_movie', args=[self.m1.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Movie.objects.filter(pk=self.m1.pk).exists())

    def test_regular_user_does_not_see_admin_buttons(self):
        html = self.client.get(reverse('catalog')).content.decode()
        self.assertNotIn('data-delete-movie', html)
        self.assertNotIn('Добавить фильм', html)

    def test_admin_adds_and_deletes_movie(self):
        self.client.logout()
        self.client.login(username='admin', password='Admin12345!')

        html = self.client.get(reverse('catalog')).content.decode()
        self.assertIn('data-delete-movie', html)
        self.assertIn('Добавить фильм', html)

        response = self.client.post(reverse('movie_add'), {
            'title': 'Новый фильм', 'original_title': '', 'year': 2024, 'director': 'Режиссёр',
            'duration': 100, 'rating': '7.5', 'description': 'Описание',
            'genres': [self.drama.pk, self.comedy.pk],
        })
        movie = Movie.objects.get(title='Новый фильм')
        self.assertRedirects(response, reverse('movie_detail', args=[movie.pk]))
        self.assertEqual(movie.genres.count(), 2)

        self.assertEqual(self.client.get(reverse('movie_partial'), {'q': 'новый'}).json()['count'], 1)

        data = self.client.post(reverse('delete_movie', args=[movie.pk])).json()
        self.assertTrue(data['ok'])
        self.assertFalse(Movie.objects.filter(pk=movie.pk).exists())

    def test_admin_form_validation(self):
        self.client.logout()
        self.client.login(username='admin', password='Admin12345!')
        response = self.client.post(reverse('movie_add'), {
            'title': 'Плохой', 'year': 1700, 'director': 'X', 'duration': 90,
            'rating': '15', 'genres': [self.drama.pk]})
        self.assertEqual(response.status_code, 200)    # форма вернулась с ошибками
        self.assertFalse(Movie.objects.filter(title='Плохой').exists())

    def test_deleting_movie_removes_marks_and_ratings(self):
        Mark.objects.create(user=self.user, movie=self.m1, kind='watch')
        Rating.objects.create(user=self.user, movie=self.m1, score=8)
        self.client.logout()
        self.client.login(username='admin', password='Admin12345!')
        self.client.post(reverse('delete_movie', args=[self.m1.pk]))
        self.assertEqual(Mark.objects.count(), 0)
        self.assertEqual(Rating.objects.count(), 0)


    def test_advanced_filters(self):
        self.m1.country = 'США'
        self.m1.save()
        self.m2.country = 'США'
        self.m2.save()
        self.m3.country = 'Франция'
        self.m3.save()
        Movie.objects.filter(pk=self.m3.pk).update(year=1990)
        url = reverse('movie_partial')
        get = lambda **p: self.client.get(url, p).json()['count']
        self.assertEqual(get(countries='США'), 2)
        self.assertEqual(get(countries='США,Франция'), 3)
        self.assertEqual(get(year_from='1994'), 2)
        self.assertEqual(get(year_to='1993'), 1)
        self.assertEqual(get(rating_min='9'), 1)
        self.assertEqual(get(duration='short'), 0)
        self.assertEqual(get(duration='medium'), 3)
        self.assertEqual(get(countries='США', rating_min='9', genres=str(self.drama.pk)), 1)
        self.assertEqual(self.client.get(url, {'year_from': 'abc', 'rating_min': 'x', 'duration': 'zz'}).status_code, 200)

    def test_search_page_shows_countries_and_years(self):
        self.m1.country = 'Япония'
        self.m1.save()
        html = self.client.get(reverse('search')).content.decode()
        self.assertIn('Япония', html)
        self.assertIn('1994', html)

    def test_admin_uploads_cover_file(self):
        import shutil
        import tempfile
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        tmp = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=tmp):
            self.client.logout()
            self.client.login(username='admin', password='Admin12345!')
            buf = BytesIO()
            Image.new('RGB', (20, 30), 'red').save(buf, 'PNG')
            image = SimpleUploadedFile('cover.png', buf.getvalue(), content_type='image/png')
            response = self.client.post(reverse('movie_add'), {
                'title': 'С обложкой', 'year': 2020, 'country': 'Россия', 'director': 'Х',
                'duration': 90, 'rating': '7.5', 'genres': [self.drama.pk], 'poster': image})
            self.assertEqual(response.status_code, 302)
            movie = Movie.objects.get(title='С обложкой')
            self.assertTrue(movie.poster)
            self.assertEqual(movie.country, 'Россия')
            path = movie.poster.path
            import os
            self.assertTrue(os.path.exists(path))
            self.client.post(reverse('delete_movie', args=[movie.pk]))
            self.assertFalse(os.path.exists(path))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_not_image_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.logout()
        self.client.login(username='admin', password='Admin12345!')
        fake = SimpleUploadedFile('a.png', b'not an image', content_type='image/png')
        self.client.post(reverse('movie_add'), {
            'title': 'Фальшивка', 'year': 2020, 'director': 'Х', 'duration': 90,
            'rating': '7', 'genres': [self.drama.pk], 'poster': fake})
        self.assertFalse(Movie.objects.filter(title='Фальшивка').exists())

